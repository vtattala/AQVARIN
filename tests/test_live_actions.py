from types import SimpleNamespace

import numpy as np

from vision.action_yolo import ActionModels, LABELS
from vision.live_actions import LiveActionModels, search_tiles


def test_search_tiles_cover_portrait_frame_and_stay_inside_image():
    tiles=search_tiles(720,1280)
    covered=np.zeros((1280,720),dtype=bool)
    for x1,y1,x2,y2 in tiles:
        assert 0<=x1<x2<=720 and 0<=y1<y2<=1280
        covered[y1:y2,x1:x2]=True
    assert covered.all() and len(tiles)==6


def test_independent_search_detects_without_primary_person_and_marks_crop_evidence(monkeypatch):
    monkeypatch.setattr(ActionModels,'predict',lambda *a,**k:([],[],[]))
    live=object.__new__(LiveActionModels)
    live.device='cuda:0';live.last_search=-1;live.search_cursor=0
    calls=[]
    def predict(crops,**kwargs):
        if not isinstance(crops,list):return [SimpleNamespace(boxes=[])]
        calls.append(len(crops))
        box=SimpleNamespace(cls=np.array(0),conf=np.array(.96),xyxy=np.array([[5,6,50,60]]))
        return [SimpleNamespace(boxes=[box]) for _ in crops]
    live.action=SimpleNamespace(predict=predict,names=LABELS)
    proposals,_,_=live.predict(np.zeros((1280,720,3),np.uint8),[])
    assert calls==[6] and len(proposals)==6
    assert all(p['class']=='drown' and p['evidence_source']=='search_tile' and p['crop_track_id'] is None for p in proposals)
    assert [213.,774.,258.,828.] in [p['bbox_xyxy_px'] for p in proposals]


def test_large_frames_have_bounded_search_batches(monkeypatch):
    monkeypatch.setattr(ActionModels,'predict',lambda *a,**k:([],[],[]))
    live=object.__new__(LiveActionModels)
    live.device='cuda:0';live.last_search=-1;live.search_cursor=0
    calls=[]
    def predict(crops,**kwargs):
        if not isinstance(crops,list):return [SimpleNamespace(boxes=[])]
        calls.append(len(crops));return [SimpleNamespace(boxes=[]) for _ in crops]
    live.action=SimpleNamespace(predict=predict)
    live.predict(np.zeros((2000,2000,3),np.uint8),[])
    assert calls==[6] and live.search_cursor==6


def test_resolutions_combine_into_one_observation_per_camera_frame(monkeypatch):
    from vision.live import LiveEngine
    from vision.models import Detection
    monkeypatch.setattr(ActionModels,'predict',lambda *a,**k:([],[],[]))
    live=object.__new__(LiveActionModels)
    live.device='cuda:0';live.last_search=-1;live.search_cursor=0
    def predict(image,**kwargs):
        if isinstance(image,list):return [SimpleNamespace(boxes=[]) for _ in image]
        box=SimpleNamespace(cls=np.array(0),conf=np.array(.92 if kwargs['imgsz']==640 else .85),xyxy=np.array([[30,30,65,90]]))
        return [SimpleNamespace(boxes=[box])]
    live.action=SimpleNamespace(predict=predict,names=LABELS)
    live.close=lambda:None
    detector=SimpleNamespace(device='cuda:0',detect=lambda *a:([Detection(4,'swimmer',.9,(30,30,65,90))],0))
    engine=LiveEngine(detector=detector,actions=live,rip=SimpleNamespace(predict=lambda *a:[]))
    frame=np.zeros((160,240,3),np.uint8)
    first=engine.process(frame,0,0)
    assert not first['distress_events']
    assert len(engine.distress.action_windows[3])==1
    engine.process(frame,.25,1)
    result=engine.process(frame,.5,2)
    assert len(result['distress_events'])==1
    assert result['distress_events'][0]['metrics']['distinct_predictions']==3
    assert result['distress_events'][0]['action_score']==.92
    engine.close()
