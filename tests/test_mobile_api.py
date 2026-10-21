from fastapi.testclient import TestClient
from vision.api import app


def test_mobile_health_and_local_cors():
    client = TestClient(app)
    response = client.get('/api/health', headers={'Origin': 'http://localhost:8081'})
    assert response.json()['classes'] == ['boat', 'buoy', 'jetski', 'life_saving_appliances', 'swimmer']
    assert response.headers['access-control-allow-origin'] == 'http://localhost:8081'


def test_mobile_rejects_unknown_tracking_preset():
    response = TestClient(app).post('/api/analyze-video',
        data={'tracking_preset': 'unknown'}, files={'video': ('test.mp4', b'data', 'video/mp4')})
    assert response.status_code == 400


def test_mobile_rejects_unknown_scene_type():
    response = TestClient(app).post('/api/analyze-video',
        data={'scene_type':'unknown'}, files={'video':('test.mp4',b'data','video/mp4')})
    assert response.status_code == 400

def test_upload_retries_reuse_job_without_duplicate_inference(tmp_path,monkeypatch):
    import vision.api as api
    monkeypatch.setattr(api,'RUNS',tmp_path)
    calls=[]
    monkeypatch.setattr(api,'_run_job',lambda *args:calls.append(args))
    client=TestClient(app)
    request_id='12345678-1234-4234-9234-123456789abc'
    for _ in range(2):
        response=client.post('/api/analyze-video',data={'request_id':request_id},
                             files={'video':('test.mp4',b'original bytes','video/mp4')})
        assert response.status_code==202
        assert response.json()['job_id']==request_id
    assert len(calls)==1
    assert (tmp_path/request_id/'source.mp4').read_bytes()==b'original bytes'

def test_upload_retries_wait_for_in_progress_transfer():
    import vision.api as api
    request_id='12345678-1234-4234-9234-123456789abd'
    api.UPLOADING.add(request_id)
    try:
        response=TestClient(app).post('/api/analyze-video',data={'request_id':request_id},
                       files={'video':('test.mp4',b'data','video/mp4')})
        assert response.status_code==409
    finally:
        api.UPLOADING.discard(request_id)


def test_restart_recovery_uses_saved_upload_and_exact_settings(tmp_path,monkeypatch):
    import json
    import vision.api as api
    from dataclasses import asdict
    from vision.config import PipelineConfig
    monkeypatch.setattr(api,'RUNS',tmp_path)
    calls=[]
    monkeypatch.setattr(api,'_run_job',lambda *args:calls.append(args))
    job_id='12345678-1234-4234-9234-123456789abc'
    directory=tmp_path/job_id;directory.mkdir()
    (directory/'source.mp4').write_bytes(b'video')
    config=PipelineConfig(confidence=.1,track_buffer=60,detection_mode='sliced')
    values={k:str(v) if hasattr(v,'as_posix') else v for k,v in asdict(config).items()}
    (directory/'request.json').write_text(json.dumps({'config':values,'source_name':'source.mp4','scene_type':'swimmers_only'}))
    status=directory/'status.json';status.write_text(json.dumps({'state':'processing'}))
    api.recover_jobs([status])
    assert len(calls)==1
    assert calls[0][2]==config
    assert calls[0][3]=='swimmers_only'
