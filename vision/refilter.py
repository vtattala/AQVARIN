"""Apply output exclusions to saved tracks and render the original video again."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from .exclusions import OutputExclusions
from .overlay import draw_tracks


def main():
    import cv2

    p = argparse.ArgumentParser(description=__doc__)
    for name in ("input", "tracks", "exclusions", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    jsonl = args.output.with_suffix(".jsonl")
    audit = args.output.with_suffix(".suppressed.jsonl")
    if {args.output.resolve(), jsonl.resolve(), audit.resolve()} & {args.input.resolve(), args.tracks.resolve(), args.exclusions.resolve()}:
        p.error("Outputs must not overwrite inputs")
    exclusion = OutputExclusions.load(args.exclusions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(args.input))
    width, height = int(cap.get(3)), int(cap.get(4))
    writer = cv2.VideoWriter(str(args.output), cv2.VideoWriter_fourcc(*"mp4v"), cap.get(5), (width,height))
    if not cap.isOpened() or not writer.isOpened():
        raise ValueError("Cannot open input or output video")
    frames = swimmers = removed = 0
    try:
        with args.tracks.open(encoding="utf-8") as source, jsonl.open("w",encoding="utf-8") as sink, audit.open("w",encoding="utf-8") as log:
            for line in source:
                row = json.loads(line)
                ok, frame = cap.read()
                if not ok:
                    raise ValueError("Video ended before tracking records")
                if row["frame"] != frames:
                    raise ValueError("Tracking frames must be consecutive from zero")
                original_swimmers = [o for o in row["objects"] if o["class"] == "swimmer"]
                row["objects"], rejected = exclusion.filter(row["objects"],width,height,frames)
                assert original_swimmers == [o for o in row["objects"] if o["class"] == "swimmer"], "Swimmer regression"
                swimmers += len(original_swimmers)
                removed += len(rejected)
                log.write(json.dumps({"frame":frames,"suppressed_objects":rejected})+"\n")
                sink.write(json.dumps(row)+"\n")
                rendered = [SimpleNamespace(track_id=o["track_id"], detection=SimpleNamespace(
                    bbox_xyxy=o["bbox_xyxy_px"],class_name=o["class"],confidence=o["confidence"]),
                    trail=[SimpleNamespace(**point) for point in o["trail"]]) for o in row["objects"]]
                writer.write(draw_tracks(frame, rendered))
                frames += 1
    finally:
        cap.release()
        writer.release()
    print(json.dumps({"frames":frames,"swimmer_records_preserved_exactly":swimmers,"suppressed_boat_records":removed}))


if __name__ == "__main__":
    main()
