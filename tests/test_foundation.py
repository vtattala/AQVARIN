import json
from pathlib import Path

import pytest

from vision.history import TrackHistory
from vision.models import Detection


def test_center_history_motion_and_trimming():
    history = TrackHistory(limit=2)
    first = history.update(7, Detection(0, "swimmer", 0.8, (0, 0, 10, 10)), 0, 0.0)
    second = history.update(7, Detection(0, "swimmer", 0.8, (10, 0, 20, 10)), 1, 0.5)
    third = history.update(7, Detection(0, "swimmer", 0.8, (20, 0, 30, 10)), 2, 1.0)
    assert first.detection.center == (5, 5)
    assert first.motion.speed_px_s == 0
    assert second.motion.velocity_px_s == (20, 0)
    assert third.motion.speed_px_s == 20
    assert third.track_age_frames == 3
    assert third.consecutive_observed_frames == 3
    assert [point.frame for point in history.points(7)] == [1, 2]
    assert json.loads(json.dumps(third.to_dict()))["track_id"] == 7


def test_empty_frame_and_missed_frame():
    history = TrackHistory()
    assert history.points(1) == ()
    history.update(1, Detection(0, "swimmer", 0.5, (0, 0, 2, 2)), 0, 0)
    resumed = history.update(1, Detection(0, "swimmer", 0.6, (2, 2, 4, 4)), 3, 1)
    assert resumed.missed_frames == 2
    assert resumed.consecutive_observed_frames == 1
    with pytest.raises(ValueError):
        history.update(1, resumed.detection, 3, 1)


def test_pipeline_config_rejects_missing_weights(tmp_path: Path):
    from vision.config import PipelineConfig

    with pytest.raises(FileNotFoundError):
        PipelineConfig(weights=tmp_path / "missing.pt").validate()


def test_roi_keeps_wading_region_and_rejects_land():
    from vision.roi import PolygonROI

    roi = PolygonROI([(0.4, 0), (1, 0), (1, 1), (0.4, 1)])
    wet = Detection(4, "swimmer", 0.7, (45, 40, 55, 50))
    land = Detection(4, "swimmer", 0.7, (5, 40, 15, 50))
    inside, outside = roi.filter([wet, land], 100, 100)
    assert inside == [wet]
    assert outside == [land]


def test_benchmark_gap_diagnostic(tmp_path: Path):
    from vision.benchmark import describe_tracks

    path = tmp_path / "tracks.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in [
        {"frame": 0, "objects": [{"track_id": 1}]},
        {"frame": 1, "objects": []},
        {"frame": 2, "objects": [{"track_id": 1}]},
    ]), encoding="utf-8")
    assert describe_tracks(path)["within_id_gap_frames"] == 1


def test_real_video_short_run(tmp_path: Path):
    """Genuine inference smoke test, opted in because CPU inference takes time."""
    import os
    if os.environ.get("RUN_VIDEO_TEST") != "1":
        pytest.skip("Set RUN_VIDEO_TEST=1 for genuine model/video integration")
    from vision.config import PipelineConfig, ROOT
    from vision.pipeline import analyze_video

    summary = analyze_video(ROOT / "Testing Videos" / "swimming aerial view.mp4",
                            tmp_path / "tracked.mp4", tmp_path / "tracks.jsonl",
                            PipelineConfig(image_size=640), max_frames=3)
    assert summary.frames == 3
    assert (tmp_path / "tracked.mp4").stat().st_size > 0
    lines = (tmp_path / "tracks.jsonl").read_text().splitlines()
    assert len(lines) == 3
    assert all(json.loads(line)["coordinate_space"] == "pixel" for line in lines)


def test_api_rejects_invalid_video():
    from fastapi.testclient import TestClient
    from vision.api import app

    response = TestClient(app).post("/api/analyze-video", files={"video": ("notes.txt", b"x", "text/plain")})
    assert response.status_code == 400


def test_api_rejects_invalid_roi():
    from fastapi.testclient import TestClient
    from vision.api import app

    response = TestClient(app).post(
        "/api/analyze-video", data={"roi_json": '{"coordinate_space":"normalized","polygon":[]}'},
        files={"video": ("short.mp4", b"data", "video/mp4")})
    assert response.status_code == 400


def test_api_unknown_job():
    from fastapi.testclient import TestClient
    from vision.api import app

    response = TestClient(app).get("/api/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_api_upload_process_and_download(tmp_path: Path, monkeypatch):
    """Real end-to-end upload, enabled explicitly to keep routine tests fast."""
    import os
    if os.environ.get("RUN_VIDEO_TEST") != "1":
        pytest.skip("Set RUN_VIDEO_TEST=1 for genuine model/video integration")
    import cv2
    from fastapi.testclient import TestClient
    from vision import api
    from vision.config import ROOT

    monkeypatch.setattr(api, "RUNS", tmp_path / "jobs")
    source = cv2.VideoCapture(str(ROOT / "Testing Videos" / "swimming aerial view.mp4"))
    short = tmp_path / "short.mp4"
    writer = cv2.VideoWriter(str(short), cv2.VideoWriter_fourcc(*"mp4v"), 30, (1920, 1080))
    for _ in range(3):
        ok, frame = source.read()
        assert ok
        writer.write(frame)
    writer.release()
    source.release()
    client = TestClient(api.app)
    with short.open("rb") as handle:
        response = client.post("/api/analyze-video", files={"video": ("short.mp4", handle, "video/mp4")})
    assert response.status_code == 202
    job = client.get(response.json()["status_url"]).json()
    assert job["state"] == "completed", job.get("error")
    assert job["summary"]["frames"] == 3
    assert client.get(job["video_url"]).status_code == 200
    assert len(client.get(job["tracks_url"]).text.splitlines()) == 3
    distress = client.get(job['distress_url']).json()
    assert distress['classifier']['state'] == 'ready'
    assert distress['classifier']['backend'] == 'yolo'
    assert distress['events'] == []
    rip = client.get(job['rip_current_url']).json()
    assert rip['status'] == 'complete' and rip['model']['state'] == 'ready'
    assert rip['sampled_frames'] == 1


def test_sliced_video_short_run(tmp_path: Path):
    import os
    if os.environ.get("RUN_VIDEO_TEST") != "1":
        pytest.skip("Set RUN_VIDEO_TEST=1 for genuine model/video integration")
    from vision.config import PipelineConfig, ROOT
    from vision.pipeline import analyze_video

    summary = analyze_video(ROOT / "Testing Videos" / "swimming aerial view.mp4",
                            tmp_path / "sliced.mp4", tmp_path / "sliced.jsonl",
                            PipelineConfig(image_size=640, detection_mode="sliced"), max_frames=3)
    assert summary.frames == 3
    assert summary.raw_detections > 0
    assert summary.tracked_observations > 0
