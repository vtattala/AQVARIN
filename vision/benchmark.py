"""Repeatable detector/tracker comparisons without pretending to measure accuracy."""
import argparse
import json
import logging
from dataclasses import asdict, replace
from pathlib import Path

from .config import PipelineConfig
from .pipeline import analyze_video


def describe_tracks(path: Path) -> dict:
    observations: dict[int, list[int]] = {}
    populated_frames = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        frame = json.loads(line)
        if frame["objects"]:
            populated_frames += 1
        for obj in frame["objects"]:
            observations.setdefault(obj["track_id"], []).append(frame["frame"])
    durations = [len(frames) for frames in observations.values()]
    gaps = sum(sum(b - a - 1 for a, b in zip(frames, frames[1:])) for frames in observations.values())
    return {"frames_with_tracks": populated_frames, "average_observed_track_frames":
            sum(durations) / len(durations) if durations else 0.0,
            "within_id_gap_frames": gaps}


def compare(input_path: Path, output_dir: Path, config: PipelineConfig,
            max_frames: int | None = None) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {"input": str(input_path), "ground_truth_available": False, "runs": {}}
    variants = {
        "full_botsort": replace(config, detection_mode="full", tracker="botsort"),
        "sliced_botsort": replace(config, detection_mode="sliced", tracker="botsort"),
        "full_deepocsort": replace(config, detection_mode="full", tracker="deepocsort"),
    }
    for name, variant in variants.items():
        jsonl = output_dir / f"{name}.jsonl"
        summary = analyze_video(input_path, output_dir / f"{name}.mp4", jsonl, variant, max_frames)
        report["runs"][name] = {**asdict(summary), **describe_tracks(jsonl)}
    report["note"] = ("Counts and gaps are diagnostic only. Without ground-truth annotations, "
                      "precision, recall, ID switches, and track retention cannot be measured.")
    (output_dir / "comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare full, SAHI, and alternate tracker modes")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--slice-size", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.30)
    parser.add_argument("--roi", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    report = compare(args.input, args.output_dir,
                     PipelineConfig(image_size=args.imgsz, slice_size=args.slice_size,
                                    confidence=args.conf, roi_path=args.roi), args.max_frames)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
