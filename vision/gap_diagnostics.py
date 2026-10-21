"""Find plausible detector/filter/association causes of gaps between observations."""
import argparse
import json
from collections import Counter, defaultdict
from math import hypot
from pathlib import Path


def analyze_gaps(tracks_path: Path, diagnostics_path: Path, radius_px: float = 80) -> dict:
    observations = defaultdict(list)
    tracked_frames = {}
    for line in tracks_path.read_text(encoding="utf-8").splitlines():
        frame = json.loads(line)
        tracked_frames[frame["frame"]] = frame
        for obj in frame["objects"]:
            observations[obj["track_id"]].append((frame["frame"], obj))
    diagnostics = {row["frame"]: row for row in map(json.loads, diagnostics_path.read_text(encoding="utf-8").splitlines())}
    episodes = []
    class_switches = []
    for track_id, items in observations.items():
        for (start_frame, start), (end_frame, end) in zip(items, items[1:]):
            if start["class"] != end["class"]:
                class_switches.append({"track_id": track_id, "from_frame": start_frame,
                                       "to_frame": end_frame, "from_class": start["class"],
                                       "to_class": end["class"]})
            gap = end_frame - start_frame - 1
            if not gap:
                continue
            counts = Counter()
            nearby_other_ids = set()
            for frame_number in range(start_frame + 1, end_frame):
                fraction = (frame_number - start_frame) / (end_frame - start_frame)
                expected = [a + (b - a) * fraction for a, b in zip(start["center_px"], end["center_px"])]
                frame_diag = diagnostics[frame_number]
                for field, label in (("kept_detections", "kept"), ("roi_rejections", "roi_rejected"),
                                     ("size_rejections", "size_rejected")):
                    near = [d for d in frame_diag[field] if d["class"] == start["class"] and
                            hypot(d["center_px"][0] - expected[0], d["center_px"][1] - expected[1]) <= radius_px]
                    if near:
                        counts[label] += 1
                for obj in tracked_frames[frame_number]["objects"]:
                    if (obj["track_id"] != track_id and obj["class"] == start["class"] and
                            hypot(obj["center_px"][0] - expected[0], obj["center_px"][1] - expected[1]) <= radius_px):
                        nearby_other_ids.add(obj["track_id"])
            episodes.append({"track_id": track_id, "start_frame": start_frame, "end_frame": end_frame,
                             "gap_frames": gap, "nearby_kept_detection_frames": counts["kept"],
                             "nearby_roi_rejection_frames": counts["roi_rejected"],
                             "nearby_size_rejection_frames": counts["size_rejected"],
                             "nearby_other_track_ids": sorted(nearby_other_ids)})
    return {
        "tracks_with_gaps": len({item["track_id"] for item in episodes}),
        "gap_episodes": len(episodes),
        "gap_frames_total": sum(item["gap_frames"] for item in episodes),
        "episodes_with_nearby_kept_detections": sum(item["nearby_kept_detection_frames"] > 0 for item in episodes),
        "episodes_with_nearby_roi_rejections": sum(item["nearby_roi_rejection_frames"] > 0 for item in episodes),
        "episodes_with_nearby_size_rejections": sum(item["nearby_size_rejection_frames"] > 0 for item in episodes),
        "episodes_with_nearby_other_ids": sum(bool(item["nearby_other_track_ids"]) for item in episodes),
        "class_switches_within_track": len(class_switches),
        "class_switch_examples": class_switches[:20],
        "longest_gap_episodes": sorted(episodes, key=lambda x: x["gap_frames"], reverse=True)[:20],
        "all_episodes": episodes,
        "method": (f"Nearby means same model class within {radius_px:g} pixels of a linearly interpolated "
                   "track center. These are diagnostic candidates, not proven identity switches or missed swimmers."),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose track gaps using pre-tracker detections")
    parser.add_argument("--tracks", type=Path, required=True)
    parser.add_argument("--diagnostics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--radius-px", type=float, default=80)
    args = parser.parse_args()
    if args.radius_px <= 0:
        parser.error("Radius must be positive")
    result = analyze_gaps(args.tracks, args.diagnostics, args.radius_px)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in {"all_episodes", "longest_gap_episodes", "class_switch_examples"}}, indent=2))


if __name__ == "__main__":
    main()
