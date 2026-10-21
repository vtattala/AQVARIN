"""Run upstream architectures in a separate interpreter to isolate their imports.

Invoked by distress.py, never imported into the identification pipeline.
No random-weight fallback. Inputs follow upstream BaseTransform (RGB 0..255).
"""
import argparse
from collections import deque
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace


def run(settings_path, source, destination):
    settings = json.loads(Path(settings_path).read_text(encoding="utf-8"))
    root = Path(settings["repository"]).resolve()
    sys.path.insert(0, str(root))
    import cv2
    import numpy as np
    from PIL import Image
    import torch
    from config import yowo_v2_config
    from models import build_model

    cfg = dict(importlib.import_module("config." + settings["architecture"]).config)
    if tuple(cfg["label_map"]) != ("swim", "drown") or cfg["multi_hot"]:
        raise ValueError("Checkpoint config must have one-hot swim/drown labels")
    device = torch.device(settings.get("device", "cpu"))
    model, _ = build_model(SimpleNamespace(), cfg, yowo_v2_config[cfg["version"]], device,
                           num_classes=2, trainable=False)
    # Fail on incompatible parameters; do not silently discard classifier weights.
    checkpoint = torch.load(settings["checkpoint"], map_location="cpu", weights_only=True)
    state = checkpoint["model"] if "model" in checkpoint else checkpoint
    model.load_state_dict(state, strict=True)
    model.to(device).eval()
    cap = cv2.VideoCapture(str(source))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not cap.isOpened() or not np.isfinite(fps) or fps <= 0:
        raise ValueError("Cannot read source video / frame rate")
    # Lifeguard training uses 30 fps; resample by time, rather than changing the
    # temporal meaning of S_distance/T_distance for a different source FPS.
    mode = cfg["mode"]
    step = cfg["T_distance"] if mode == "reference" else cfg["S_distance"]
    warmup_s = max(4., ((cfg["T_len"]-1)*cfg["T_distance"] if mode == "reference"
                       else (cfg["S_len"]-1)*cfg["S_distance"]) / 30)
    buffer = deque(maxlen=1 + (cfg["T_len"] - 1) * cfg["T_distance"])
    hidden = [[None, None, None], [None, None, None]] if mode == "2Dseq" else None
    tick = 0
    index = 0
    previous = None
    context_start = 0.
    with Path(destination).open("w", encoding="utf-8") as out, torch.inference_mode():
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            t = index / fps
            tensor = torch.from_numpy(np.asarray(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)).resize(
                (cfg["test_size"], cfg["test_size"]))).copy()).permute(2, 0, 1).float()
            gray = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (64, 64))
            cut = previous is not None and float(np.mean(cv2.absdiff(gray, previous))) > 45
            previous = gray
            if cut:
                buffer.clear()
                context_start = t
                hidden = [[None, None, None], [None, None, None]] if mode == "2Dseq" else None
            # Decode once, use the most recent source frame for each 30 Hz tick.
            latest = None
            while tick / 30 <= t + 1e-6:
                buffer.append(tensor)
                if tick % step == 0:
                    if mode == "2Dseq":
                        inputs = tensor[None, None].to(device)  # S,B,C,H,W
                        scores, labels, boxes, hidden = model(inputs, hidden)
                    elif len(buffer) == buffer.maxlen:
                        clip = torch.stack(list(buffer)[::cfg["T_distance"]], dim=1)[None].to(device)
                        if mode == "reference":
                            scores, labels, boxes = model(clip)
                        else:
                            scores, labels, boxes, hidden = model(clip[None], hidden)
                    else:
                        tick += 1
                        continue
                    width, height = bgr.shape[1], bgr.shape[0]
                    latest = [{"class": ("swim", "drown")[int(label)], "score": float(score),
                               "bbox_xyxy_px": (box * np.array([width, height, width, height])).tolist()}
                              for score, label, box in zip(scores[0], labels[0], boxes[0])]
                tick += 1
            if latest is not None:
                out.write(json.dumps({"frame": index, "timestamp_s": t, "context_s": t-context_start,
                                      "context_ready": t-context_start >= warmup_s, "proposals": latest}) + "\n")
            index += 1
    cap.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("settings")
    parser.add_argument("source")
    parser.add_argument("output")
    args = parser.parse_args()
    run(args.settings, args.source, args.output)
