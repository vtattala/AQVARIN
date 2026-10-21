import json

from vision.geometry import filter_oversized_swimmers
from vision.gap_diagnostics import analyze_gaps
from vision.models import Detection


def test_size_guard_is_optional_and_class_specific():
    giant = Detection(4, "swimmer", .8, (0, 0, 50, 50))
    small = Detection(4, "swimmer", .8, (0, 0, 10, 10))
    boat = Detection(0, "boat", .8, (0, 0, 80, 80))
    detections = [giant, small, boat]
    assert filter_oversized_swimmers(detections, 100, 100, None) == (detections, [])
    assert filter_oversized_swimmers(detections, 100, 100, .05) == ([small, boat], [giant])


def test_gap_diagnosis_distinguishes_detection_filter_and_association(tmp_path):
    def obj(track_id, center):
        return {"track_id": track_id, "class": "swimmer", "center_px": center}

    tracks = [
        {"frame": 0, "objects": [obj(1, [0, 0])]},
        {"frame": 1, "objects": [obj(2, [10, 0])]},
        {"frame": 2, "objects": []},
        {"frame": 3, "objects": [obj(1, [30, 0])]},
        {"frame": 4, "objects": []},
        {"frame": 5, "objects": [obj(1, [50, 0])]},
    ]
    diagnostics = [{"frame": i, "kept_detections": [], "roi_rejections": [],
                    "size_rejections": []} for i in range(6)]
    diagnostics[1]["kept_detections"] = [obj(2, [10, 0])]
    diagnostics[2]["roi_rejections"] = [obj(3, [20, 0])]
    for name, rows in (("tracks", tracks), ("diagnostics", diagnostics)):
        (tmp_path / name).write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
    result = analyze_gaps(tmp_path / "tracks", tmp_path / "diagnostics", radius_px=2)
    assert result["gap_episodes"] == 2
    assert result["gap_frames_total"] == 3
    assert result["episodes_with_nearby_kept_detections"] == 1
    assert result["episodes_with_nearby_roi_rejections"] == 1
    assert result["episodes_with_nearby_other_ids"] == 1
    assert result["all_episodes"][1]["nearby_kept_detection_frames"] == 0
