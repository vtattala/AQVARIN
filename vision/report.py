"""Summarize JSONL tracks without treating detections as ground truth."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median


def summarize(jsonl: Path, width: int, height: int,
              watermark_box: tuple[int, int, int, int] | None = None) -> tuple[dict, list[dict]]:
    frames = []
    tracks: dict[int, list[tuple[int, dict]]] = defaultdict(list)
    classes = Counter()
    confidences = []
    oversized = []
    watermark_intersections = 0
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        frame = json.loads(line)
        frames.append(frame)
        for obj in frame["objects"]:
            tracks[obj["track_id"]].append((frame["frame"], obj))
            classes[obj["class"]] += 1
            confidences.append(obj["confidence"])
            x1, y1, x2, y2 = obj["bbox_xyxy_px"]
            if (x2 - x1) * (y2 - y1) > 0.05 * width * height:
                oversized.append({"frame": frame["frame"], "track_id": obj["track_id"],
                                  "class": obj["class"], "bbox_xyxy_px": obj["bbox_xyxy_px"]})
            if watermark_box:
                a, b, c, d = watermark_box
                if max(x1, a) < min(x2, c) and max(y1, b) < min(y2, d):
                    watermark_intersections += 1
    track_rows = []
    for track_id, observations in sorted(tracks.items()):
        first, last = observations[0][0], observations[-1][0]
        counts = Counter(obj["class"] for _, obj in observations)
        gaps = sum(b[0] - a[0] - 1 for a, b in zip(observations, observations[1:]))
        track_rows.append({"track_id": track_id, "primary_class": counts.most_common(1)[0][0],
                           "observations": len(observations), "first_frame": first, "last_frame": last,
                           "span_frames": last - first + 1, "gap_frames": gaps,
                           "mean_confidence": round(mean(obj["confidence"] for _, obj in observations), 4)})
    summary = {
        "input_jsonl": str(jsonl), "frames": len(frames),
        "duration_s": frames[-1]["timestamp_s"] if frames else 0,
        "frames_with_tracks": sum(bool(frame["objects"]) for frame in frames),
        "tracked_observations": sum(classes.values()),
        "tracked_observations_by_class": dict(classes),
        "unique_track_ids": len(tracks),
        "track_ids_by_primary_class": dict(Counter(row["primary_class"] for row in track_rows)),
        "max_simultaneous_tracks": max((len(frame["objects"]) for frame in frames), default=0),
        "confidence_min": min(confidences) if confidences else None,
        "confidence_median": median(confidences) if confidences else None,
        "confidence_max": max(confidences) if confidences else None,
        "median_observations_per_track": median([row["observations"] for row in track_rows]) if track_rows else 0,
        "tracks_with_observation_gaps": sum(row["gap_frames"] > 0 for row in track_rows),
        "within_id_gap_frames_total": sum(row["gap_frames"] for row in track_rows),
        "gap_episodes": sum(sum(b[0] > a[0] + 1 for a, b in zip(items, items[1:]))
                            for items in tracks.values()),
        "oversized_boxes_over_5_percent_frame_count": len(oversized),
        "oversized_box_sample": oversized[:5] + (oversized[-5:] if len(oversized) > 5 else []),
        "approximate_watermark_box_px": watermark_box,
        "boxes_intersecting_approximate_watermark_region": watermark_intersections,
        "caution": "Detections, track IDs, and watermark intersections are model outputs, not verified object counts or accuracy metrics.",
    }
    return summary, track_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize a tracking JSONL file")
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--watermark-box", nargs=4, type=int)
    args = parser.parse_args()
    summary, rows = summarize(args.jsonl, args.width, args.height,
                              tuple(args.watermark_box) if args.watermark_box else None)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (args.output_dir / "tracks.csv").open("w", newline="", encoding="utf-8") as sink:
        writer = csv.DictWriter(sink, fieldnames=list(rows[0]) if rows else ["track_id"])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
