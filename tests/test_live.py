import json
import threading
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from vision.live import LiveEngine, LiveSessions, LiveTracks, LiveVisibilityWatch, decode_camera_frame, recover_known_swimmers
from vision.models import Detection


def jpeg():
    return cv2.imencode('.jpg',np.full((160,240,3),60,np.uint8))[1].tobytes()


class Detector:
    device='cpu'
    visible=True
    def detect(self,frame):
        return ([Detection(4,'swimmer',.9,(30,30,65,90)),Detection(0,'boat',.8,(120,30,200,90))] if self.visible else []),0


class Actions:
    visible=True
    def predict(self,frame,objects):
        return ([{'class':'drown','label':'Active drowning','score':.95,'bbox_xyxy_px':[30,30,65,90]}] if self.visible else []),[],[]
    def close(self):pass


class Rip:
    def predict(self,frame):return [{'label':'sediment_rip','score':.9,'bbox_xyxy_px':[80,100,200,150]}]


def engine(scene='auto'):
    return LiveEngine(scene,detector=Detector(),actions=Actions(),rip=Rip())


def test_live_persistent_ids_actions_rips_and_exact_analyzed_jpeg():
    live=engine();frame=cv2.imdecode(np.frombuffer(jpeg(),np.uint8),cv2.IMREAD_COLOR)
    ids=[]
    for i,t in enumerate([0,.5,1]):
        result=live.process(frame,t,i)
        ids.append([o['track_id'] for o in result['tracking']['objects']])
    assert ids[0]==ids[1]==ids[2]
    assert len(result['distress_events'])==1
    assert result['distress_events'][0]['action_score']==pytest.approx(.95)
    assert len(result['rip_events'])==1
    assert result['models']['identification']['state']=='ready'
    assert result['image_base64'] and result['sequence']==2
    assert result['width_px']==240 and result['height_px']==160
    assert len(set(ids[0]))==len(ids[0])
    assert all(o['track_id']%2==(1 if o['class']=='swimmer' else 0) for o in result['tracking']['objects'])
    live.close()


def test_live_missing_swimmer_and_reacquisition():
    live=engine();frame=decode_camera_frame(jpeg())
    first=live.process(frame,0,0)
    tid=next(o['track_id'] for o in first['tracking']['objects'] if o['class']=='swimmer')
    live.detector.visible=live.actions.visible=False
    missing=live.process(frame,.5,1)
    assert missing['tracking']['unobserved_swimmers'][0]['track_id']==tid
    assert missing['tracking']['unobserved_swimmers'][0]['confidence'] is None
    live.detector.visible=live.actions.visible=True
    returned=live.process(frame,1,2)
    assert next(o['track_id'] for o in returned['tracking']['objects'] if o['class']=='swimmer')==tid
    live.close()


def test_live_sidecar_runtime_failure_preserves_identification():
    live=engine()
    def fail(*args):raise RuntimeError('sidecar unavailable')
    live.actions.predict=fail;live.rip.predict=fail
    result=live.process(decode_camera_frame(jpeg()),0,0)
    assert len(result['tracking']['objects'])==2
    assert result['models']['drowning']['state']=='failed'
    assert result['models']['rip_current']['state']=='failed'
    live.close()


def test_live_swimmers_only_excludes_vessels_without_mutating_detection():
    live=engine('swimmers_only')
    assert [o['class'] for o in live.process(decode_camera_frame(jpeg()),0,0)['tracking']['objects']]==['swimmer']
    assert len(live.detector.detect(None)[0])==2
    live.close()


def test_live_resets_temporal_evidence_after_gap():
    live=engine();frame=decode_camera_frame(jpeg())
    live.process(frame,0,0);live.process(frame,.5,1)
    result=live.process(frame,4,2)
    assert not result['distress_events'] and not result['rip_events']
    live.close()


def test_live_wall_clock_evidence_supports_slower_camera_sampling():
    live=engine();frame=decode_camera_frame(jpeg())
    for i,t in enumerate([0,1.6,3.2]): result=live.process(frame,t,i)
    assert len(result['distress_events'])==1 and len(result['rip_events'])==1
    assert result['distress_events'][0]['metrics']['distinct_predictions']==3
    assert result['alert_policy']['window_seconds']==6
    live.close()


def test_camera_frame_validation():
    assert decode_camera_frame(jpeg()).shape==(160,240,3)
    for value in [b'',b'not an image',b'x'*2_000_001]:
        with pytest.raises(Exception): decode_camera_frame(value)
    png=cv2.imencode('.png',np.zeros((64,64,3),np.uint8))[1].tobytes()
    with pytest.raises(ValueError):decode_camera_frame(png)


def test_api_live_session_frame_stop_and_stale_frames(monkeypatch):
    from vision import live
    from vision.api import app
    manager=LiveSessions(factory=engine)
    monkeypatch.setattr(live,'sessions',manager)
    client=TestClient(app)
    response=client.post('/api/live/sessions',json={'scene_type':'auto'})
    assert response.status_code==201
    key=response.json()['session_id'];url=f'/api/live/sessions/{key}/frame'
    headers={'Content-Type':'image/jpeg','X-Frame-Sequence':'0','X-Captured-At':'0'}
    assert client.post(url,content=jpeg(),headers=headers).json()['sequence']==0
    diagnostics=client.get(f'/api/live/sessions/{key}/diagnostics').json()
    assert len(diagnostics)==1 and 'image_base64' not in json.dumps(diagnostics)
    assert client.get(f'/api/live/sessions/{key}/diagnostic-frame').status_code==403
    assert client.post(url,content=jpeg(),headers=headers).status_code==409
    assert client.post(url,content=jpeg(),headers={**headers,'X-Frame-Sequence':'1','X-Captured-At':'nan'}).status_code==400
    assert client.post(url,content=jpeg(),headers={**headers,'Content-Type':'video/mp4'}).status_code==415
    assert client.delete(f'/api/live/sessions/{key}').status_code==204
    assert client.get(f'/api/live/sessions/{key}/diagnostics').status_code==410
    assert client.post(url,content=jpeg(),headers=headers).status_code==410
    assert client.delete(f'/api/live/sessions/{key}').status_code==204
    assert client.post('/api/live/sessions',json={'scene_type':'wrong'}).status_code==400


def test_live_capacity_idle_expiry_and_independent_ids(monkeypatch):
    import vision.live as module
    manager=LiveSessions(factory=engine,limit=1)
    first=manager.start('auto')['session_id']
    with pytest.raises(HTTPException) as error:manager.start('auto')
    assert error.value.status_code==429
    manager.sessions[first].touched-=121
    manager.reap()
    assert not manager.sessions
    second=manager.start('auto')['session_id']
    assert second!=first
    manager.close()


def test_live_backpressure_rejects_concurrent_frame():
    manager=LiveSessions(factory=engine)
    key=manager.start('auto')['session_id']
    entered=threading.Event();release=threading.Event()
    original=manager.sessions[key].engine.process
    def slow(*args):
        entered.set();release.wait(5);return original(*args)
    manager.sessions[key].engine.process=slow
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(manager.process,key,jpeg(),0,0)
        assert entered.wait(2)
        try:
            with pytest.raises(HTTPException) as error:manager.process(key,jpeg(),1,.5)
            assert error.value.status_code==409
        finally:release.set()
        assert future.result()['sequence']==0
    manager.close()


def test_live_does_not_use_or_reset_original_tracker_counter():
    from ultralytics.trackers.basetrack import BaseTrack
    before=BaseTrack._count
    live=engine()
    live.process(decode_camera_frame(jpeg()),0,0)
    assert BaseTrack._count==before
    live.close()


def test_live_low_confidence_continues_known_tracks_without_starting_noise():
    tracks=LiveTracks()
    first=tracks.update([Detection(4,'swimmer',.8,(30,30,65,90))],0,0)[0]
    result=tracks.update([Detection(4,'swimmer',.14,(31,30,66,90)),
                          Detection(4,'swimmer',.15,(150,30,170,90)),
                          Detection(0,'boat',.12,(30,30,65,90))],1,.2)
    assert len(result)==1 and result[0]['track_id']==first['track_id']
    assert result[0]['confidence']==.14  # Preserve actual model confidence.
    assert not tracks.update([Detection(4,'swimmer',.14,(31,30,66,90))],2,4)


def test_person_recovery_requires_recent_unambiguous_known_swimmer():
    human={'class':'person','score':.8,'bbox_xyxy_px':[30,30,65,90]}
    assert recover_known_swimmers([human],[],{},1)==[]
    remembered={1:{'box':[30,30,65,90],'time':0}}
    assert recover_known_swimmers([human],[],remembered,1)==[human]
    assert recover_known_swimmers([human],[],remembered,4)==[]
    remembered[3]={'box':[31,30,66,90],'time':0}
    assert recover_known_swimmers([human],[],remembered,1)==[]


def test_live_submersion_keeps_id_and_evidence_without_inventing_predictions():
    live=engine();frame=decode_camera_frame(jpeg())
    initial=live.process(frame,0,0)
    tid=next(o['track_id'] for o in initial['tracking']['objects'] if o['class']=='swimmer')
    live.process(frame,.4,1)
    live.detector.visible=live.actions.visible=False
    for i,t in enumerate([1.2,2.2,3],2):
        result=live.process(frame,t,i)
        assert len(result['distress_events'])==1
        assert result['distress_events'][0]['metrics']['distinct_predictions']==2
        assert result['distress_events'][0]['signals']==['active_drowning','visual_contact_lost']
        assert not result['tracking']['objects']
        lost=result['tracking']['unobserved_swimmers'][0]
        assert lost['track_id']==tid and lost['action_score'] is None
        assert len(live.distress.action_windows[tid])==2
    live.detector.visible=live.actions.visible=True
    returned=live.process(frame,3.3,5)
    assert next(o['track_id'] for o in returned['tracking']['objects'] if o['class']=='swimmer')==tid
    assert len(returned['distress_events'])==1
    assert returned['distress_events'][0]['metrics']['distinct_predictions']==2
    live.close()


def test_live_normal_swimming_does_not_raise_drowning_warning():
    live=engine();frame=decode_camera_frame(jpeg())
    live.actions.predict=lambda *args:([{'class':'swim','label':'Swimming','score':.95,'bbox_xyxy_px':[30,30,65,90]}],[],[])
    for i in range(10):
        result=live.process(frame,i*.25,i)
        assert not result['distress_events']
    live.close()


def test_live_low_confidence_observation_is_not_also_reported_as_missing():
    live=engine();frame=decode_camera_frame(jpeg())
    live.process(frame,0,0)
    live.actions.visible=False
    live.detector.detect=lambda *args:([Detection(4,'swimmer',.14,(31,30,66,90))],0)
    result=live.process(frame,.3,1)
    assert result['tracking']['objects'][0]['confidence']==.14
    assert not result['tracking']['unobserved_swimmers']
    live.close()


@pytest.mark.parametrize('votes,crop,score',[(1,False,.95),(2,True,.95),(2,False,.7)])
def test_lost_contact_alone_or_weak_actions_cannot_raise_warning(votes,crop,score):
    live=engine();frame=decode_camera_frame(jpeg())
    def action(*args):
        proposal={'class':'drown','label':'Active drowning','score':score,'bbox_xyxy_px':[30,30,65,90]}
        if crop:proposal['crop_track_id']=3
        return [proposal],[],[]
    live.actions.predict=action
    for i in range(votes):live.process(frame,i*.4,i)
    live.detector.visible=False;live.actions.predict=lambda *args:([],[],[])
    result=live.process(frame,1.5,votes)
    assert not result['distress_events']
    live.close()


def test_live_diagnostics_do_not_retain_camera_images():
    manager=LiveSessions(factory=engine)
    key=manager.start('auto')['session_id']
    manager.process(key,jpeg(),0,0)
    snapshot=manager.diagnostic_frame(key)
    assert snapshot.body==jpeg() and snapshot.headers['x-frame-sequence']=='0'
    rows=manager.diagnostics(key)
    assert len(rows)==1 and rows[0]['swimmers']
    assert 'image_base64' not in json.dumps(rows)
    rows[0]['swimmers'].clear()
    assert manager.diagnostics(key)[0]['swimmers']
    manager.close()


def test_missing_distressed_swimmer_gets_search_priority_and_eight_second_marker():
    watch=LiveVisibilityWatch()
    objects=[{'track_id':i,'class':'swimmer','confidence':.9,'bbox_xyxy_px':[i*10,0,i*10+8,20]} for i in range(12)]
    objects[-1]['distress_action']={'label':'Active drowning','score':.9,'requires_review':True}
    watch.update(objects,0)
    assert watch.rois(.5)[0]['track_id']==11
    # No new action prediction: keep its historical label only in memory.
    weak={**objects[-1],'confidence':.14};weak.pop('distress_action')
    watch.update([weak],.5)
    lost=watch.update([],4)
    assert len(lost)==1 and lost[0]['track_id']==11 and lost[0]['last_action']['score']==.9
    assert not watch.rois(4)  # Stale positions do not launch inference crops.
    assert not watch.update([],8.6)
