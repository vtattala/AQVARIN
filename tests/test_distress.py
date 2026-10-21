import copy
import hashlib
import json

from vision.distress import DistressEngine, analyze_distress, associate, settings_from_file


def swimmer(tid, x=0, y=0):
    return {"track_id": tid, "class": "swimmer", "confidence": .9, "center_px": [x,y],
            "bbox_xyxy_px": [x-5,y-5,x+5,y+5]}


def record(t, objects):
    return {"frame": round(t*30), "timestamp_s": t, "objects": objects}


def test_no_checkpoint_and_tracks_immutable(tmp_path):
    tracks = tmp_path / "tracks.jsonl"
    tracks.write_text('\n'.join(json.dumps(record(i/30, [swimmer(1)])) for i in range(300)))
    cfg = tmp_path/'z5cc.json'
    cfg.write_text(json.dumps({'backend':'z5cc'}))
    before = hashlib.sha256(tracks.read_bytes()).digest()
    report = analyze_distress("unused.mp4", tracks, tmp_path / "distress.json", cfg)
    assert report["classifier"]["state"] == "missing_checkpoint"
    assert report["events"] == []
    assert before == hashlib.sha256(tracks.read_bytes()).digest()
    assert len(report["indicator_capabilities"]) == 8
    assert all(s["swimmers"][0]["state"] == "undetermined" for s in report["samples"])


def test_missing_configured_checkpoint_is_explicit_not_random_inference(tmp_path):
    tracks = tmp_path / 'tracks.jsonl'
    tracks.write_text(json.dumps(record(0, [swimmer(1)])))
    cfg = tmp_path / 'config.json'
    cfg.write_text(json.dumps({'checkpoint': str(tmp_path/'missing.pth')}))
    report = analyze_distress('unused.mp4', tracks, tmp_path/'distress.json', cfg)
    assert report['classifier']['state'] == 'failed'
    assert 'does not exist' in report['classifier']['message']
    assert report['events'] == []


def test_no_false_distress_from_stationary_swimmer_or_track_gaps():
    cfg = settings_from_file()
    cfg.update(motion_reference="stationary", water_confirmed=True)
    engine = DistressEngine(cfg)
    for i in range(300):
        engine.update(record(i/30, [swimmer(1)]))
    assert not engine.events  # Resting/floating alone is not a distress warning.
    engine.update(record(20, [swimmer(1)]))
    assert len(engine.history[1]) == 1


def test_association_rejects_ambiguous_people():
    proposal = {"class":"drown", "score":.99, "bbox_xyxy_px":[-5,-5,5,5]}
    assert associate([swimmer(1), swimmer(2, 1)], [proposal]) == {}
    assert associate([swimmer(1), swimmer(2, 30)], [proposal])[1] == proposal


def test_neural_warning_persists_and_expires_without_observation():
    engine = DistressEngine(settings_from_file())
    objects = [swimmer(1)]
    saved = copy.deepcopy(objects)
    p = [{"class":"drown", "score":.9, "bbox_xyxy_px":[-5,-5,5,5]}]
    for i in range(80):
        engine.update(record(i/30, objects), p, context_s=5)
    assert len(engine.events) == 1
    assert engine.events[0]["requires_review"]
    assert objects == saved
    engine.update(record(3, []), p, context_s=5)
    assert not engine.pending


def test_camera_or_water_unverified_blocks_motion_warnings():
    cfg = settings_from_file()
    cfg.update(offshore_direction=[1,0])
    engine = DistressEngine(cfg)
    # One swimmer steadily drifts away from a nearby swimmer.
    for i in range(210):
        t = i/30
        engine.update(record(t, [swimmer(1, t*20), swimmer(2, 20)]))
    assert not engine.events


def test_verified_offshore_drift_and_separation_warn_after_persistence():
    cfg = settings_from_file()
    cfg.update(motion_reference="stationary", water_confirmed=True, offshore_direction=[1,0])
    engine = DistressEngine(cfg)
    for i in range(210):
        t = i/30
        engine.update(record(t, [swimmer(1, t*20), swimmer(2, 20)]))
    assert len(engine.events) == 1
    assert set(engine.events[0]['signals']) == {'offshore_drift', 'swimmer_separation'}
    assert engine.events[0]['timestamp_s'] >= 6


def test_isolated_sidecar_failure_preserves_successful_api_job(tmp_path, monkeypatch):
    import vision.api as api
    from dataclasses import dataclass
    @dataclass
    class Summary:
        frames: int = 1
    monkeypatch.setattr(api, 'RUNS', tmp_path)
    monkeypatch.setattr(api, 'analyze_video', lambda *a: Summary())
    monkeypatch.setattr(api, 'prepare_playback', lambda *a: None)
    monkeypatch.setattr(api, 'enrich_video', lambda *a: None)
    def fail(*a):
        raise ValueError('invalid distress config')
    monkeypatch.setattr(api, 'analyze_distress', fail)
    job_id = '12345678-1234-1234-1234-123456789abc'
    source = tmp_path/job_id/'source.mp4'
    source.parent.mkdir()
    api._run_job(job_id, source, None)
    job = api.get_job(job_id)
    assert job['state'] == 'completed'
    assert job['distress_status'] == 'failed'
    assert 'tracks_url' in job and 'distress_url' in job
