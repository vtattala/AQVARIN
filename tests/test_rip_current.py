import json

import cv2
import numpy as np
from fastapi.testclient import TestClient

from vision.rip_current import RipEvidence, RipScoutModel, analyze_rip_current, decode_predictions


def region(box=None,score=.8):
    return {'label':'sediment_rip','score':score,'bbox_xyxy_px':box or [10,20,60,80]}


def test_output_mapping_and_clipping():
    result = decode_predictions([[-.1,.1,.5,1.2],[.1,.1,.5,.5]], [0,1], [.8,.99],2,200,100)
    assert len(result)==1
    assert np.allclose(result[0]['bbox_xyxy_px'],[20,0,200,50])
    assert result[0]['label']=='sediment_rip'


def test_transient_and_cached_predictions_do_not_warn():
    evidence=RipEvidence()
    for _ in range(5): evidence.update([region()],0,0)
    evidence.update([],10,.5)
    assert evidence.events==[]


def test_persistent_region_warns_once_with_original_scores():
    evidence=RipEvidence()
    for i,score in enumerate([.7,.8,.9,.8]): evidence.update([region(score=score)],i,i*.5)
    assert len(evidence.events)==1
    e=evidence.events[0]
    assert e['timestamp_s']==1 and e['distinct_predictions']==3
    assert abs(e['model_score']-.8)<1e-6
    assert e['requires_review'] is True


def test_different_regions_and_absence_never_pool_votes():
    evidence=RipEvidence()
    evidence.update([region()],0,0)
    evidence.update([region([100,100,160,180])],10,.5)
    evidence.update([region()],40,2)
    assert evidence.events==[]


def test_real_checkpoint_runs_and_empty_image_does_not_warn():
    model=RipScoutModel()
    assert model.predict(np.zeros((200,320,3),dtype=np.uint8))==[]


def test_video_sampling_failure_and_preservation(tmp_path):
    source=tmp_path/'input.mp4'
    writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'mp4v'),10,(64,64))
    for _ in range(21):writer.write(np.full((64,64,3),80,dtype=np.uint8))
    writer.release()
    original=source.read_bytes()
    class Fake:
        def predict(self,frame):return [region()]
    report=analyze_rip_current(source,tmp_path/'rip.json',Fake())
    assert report['sampled_frames']==5 and len(report['events'])==1
    assert source.read_bytes()==original
    class Failed:
        def predict(self,frame):raise RuntimeError('runtime down')
    report=analyze_rip_current(source,tmp_path/'failed.json',Failed())
    assert report['status']=='failed' and report['events']==[]
    assert source.read_bytes()==original


def test_api_new_and_legacy_reports(tmp_path,monkeypatch):
    import vision.api as api
    monkeypatch.setattr(api,'RUNS',tmp_path)
    job='12345678-1234-4234-9234-123456789abc'
    folder=tmp_path/job;folder.mkdir()
    (folder/'status.json').write_text(json.dumps({'job_id':job,'state':'completed'}))
    client=TestClient(api.app)
    assert 'rip_current_url' not in client.get(f'/api/jobs/{job}').json()
    assert client.get(f'/api/jobs/{job}/rip-current').status_code==404
    (folder/'rip_current.json').write_text(json.dumps({'status':'complete','events':[]}))
    assert client.get(f'/api/jobs/{job}').json()['rip_current_url'].endswith('/rip-current')
    assert client.get(f'/api/jobs/{job}/rip-current').json()['events']==[]


def test_rip_failure_cannot_fail_identification_job(tmp_path,monkeypatch):
    from dataclasses import dataclass
    import vision.api as api
    from vision.config import PipelineConfig
    @dataclass
    class Summary:
        frames: int = 1
    monkeypatch.setattr(api,'RUNS',tmp_path)
    monkeypatch.setattr(api,'analyze_video',lambda *args:Summary())
    monkeypatch.setattr(api,'enrich_video',lambda *args:None)
    monkeypatch.setattr(api,'analyze_distress',lambda *args,**kwargs:None)
    monkeypatch.setattr(api,'prepare_playback',lambda *args:None)
    def broken(*args):raise RuntimeError('RipScout unavailable')
    monkeypatch.setattr(api,'analyze_rip_current',broken)
    job='12345678-1234-4234-9234-123456789abc'
    directory=tmp_path/job;directory.mkdir()
    source=directory/'source.mp4';source.write_bytes(b'original')
    api._run_job(job,source,PipelineConfig())
    status=json.loads((directory/'status.json').read_text())
    assert status['state']=='completed' and status['rip_current_status']=='failed'
    assert source.read_bytes()==b'original'
