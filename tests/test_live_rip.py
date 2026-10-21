import cv2
import numpy as np
import pytest

from vision.live_rip import LiveRipScoutModel, LiveRipEvidence, context_windows
from vision.rip_current import RipScoutModel


def region(box=None, score=.7, source='context_crop'):
    return {'label':'sediment_rip','score':score,'bbox_xyxy_px':box or [10,20,60,80],
            'evidence_source':source}


def test_context_search_covers_portrait_and_maps_back_without_extra_votes():
    windows=context_windows(720,1280)
    # Wide overlapping views cover every row, including both image edges.
    wide=[w for w in windows if w[2]-w[0]==720]
    assert wide[0][1]==0 and wide[-1][3]==1280
    assert all(b[1]<=a[3] for a,b in zip(wide,wide[1:]))
    class Model:
        calls=0
        def predict(self,frame):
            self.calls+=1
            return [] if self.calls==1 else [region([1,2,30,40])]
    m=Model();live=LiveRipScoutModel(m)
    predictions=live.predict(np.zeros((1280,720,3),np.uint8))
    assert m.calls==4 and live.last_diagnostics['crop_passes']==3
    for r in predictions:
        x,y,_,_=r['context_xyxy_px']
        assert r['bbox_xyxy_px']==[x+1,y+2,x+30,y+40]
    evidence=LiveRipEvidence();evidence.update(predictions,0,0)
    assert not evidence.events
    assert all(len(t['samples'])==1 for t in evidence.tracks.values())


def test_full_frame_result_and_actual_score_preserved_when_crops_overlap():
    class Model:
        def predict(self,frame):
            return [region([10,20,60,80],.5)]
    predictions=LiveRipScoutModel(Model(),crop_budget=1).predict(np.zeros((800,1280,3),np.uint8))
    assert len(predictions)==1
    assert predictions[0]['evidence_source']=='full_frame' and predictions[0]['score']==.5


def test_live_crop_warning_requires_independent_frames_span_and_peak():
    e=LiveRipEvidence()
    for i in range(5):e.update([region(score=.6)],i,i*.4)
    assert not e.events  # Crop search cannot promote repeated weak predictions.
    e.update([region(score=.8)],5,2)
    assert len(e.events)==1 and e.events[0]['distinct_predictions']==6
    assert abs(e.events[0]['model_score']-(.6*5+.8)/6)<1e-6
    e=LiveRipEvidence()
    for i,t in enumerate([0,.1,.2]):e.update([region(score=.8)],i,t)
    assert not e.events  # Three fast predictions still need one second.
    e.update([region(score=.8)],3,1)
    assert len(e.events)==1


def test_full_frame_warning_policy_is_unchanged_and_expired_sources_do_not_count():
    e=LiveRipEvidence()
    for i,t in enumerate([0,.5,1]):e.update([region(score=.5,source='full_frame')],i,t)
    assert len(e.events)==1 and e.events[0]['model_score']==.5
    e=LiveRipEvidence()
    e.update([region(source='full_frame')],0,0)
    for i,t in enumerate([2,4,6,7]):e.update([region(score=.6)],i+1,t)
    # Clear the original event, then inspect the window: stale full-frame
    # evidence cannot bypass the stronger crop rule.
    e.events.clear();next(iter(e.tracks.values()))['warned']=False
    e.update([region(score=.6)],5,8)
    assert not e.events


def test_live_model_reset_removes_focus_and_keeps_bounded_search():
    class Model:
        def predict(self,frame):return [region()]
    live=LiveRipScoutModel(Model(),crop_budget=99)
    f=np.zeros((1280,720,3),np.uint8)
    for _ in range(10):live.predict(f)
    assert live.last_diagnostics['crop_passes']<=3 and live.focus
    live.reset()
    assert not live.focus and live.index==live.cursor==0


@pytest.mark.parametrize('shape',[(800,1280),(1280,720)])
def test_persistent_candidates_never_starve_scene_wide_search(shape):
    class AlwaysPositive:
        def predict(self,frame):return [region(score=.8)]
    live=LiveRipScoutModel(AlwaysPositive())
    frame=np.zeros((*shape,3),np.uint8)
    count=len(context_windows(shape[1],shape[0]))
    # Both discovery slots continue moving with persistent candidates in
    # every previously searched view; no window can monopolize the search.
    bound=int(np.ceil(count/2))+1
    for _ in range(bound):live.predict(frame)
    assert live.last_diagnostics['coverage']['views_checked']==count
    assert live.last_diagnostics['coverage']['discovery_slots']>=2
    for _ in range(2*count):
        live.predict(frame)
        assert live.last_diagnostics['coverage']['oldest_view_age_frames']<=bound


def test_multiple_separated_candidates_in_one_frame_are_all_retained():
    class Model:
        def predict(self,frame):
            return [region([10,20,60,80],.8),region([150,20,220,80],.9)]
    live=LiveRipScoutModel(Model(),crop_budget=0)
    predictions=live.predict(np.zeros((300,300,3),np.uint8))
    assert len(predictions)==2
    evidence=LiveRipEvidence()
    for i,t in enumerate([0,.5,1]):evidence.update([dict(p) for p in predictions],i,t)
    assert len(evidence.events)==2 and len({e['region_id'] for e in evidence.events})==2


def test_real_checkpoint_retains_labeled_sediment_example_with_context_search():
    from vision.config import ROOT
    fixture=ROOT/'outputs/ripscout-validation/ripimage01902.jpg'
    if not fixture.is_file():
        pytest.skip('Optional upstream annotated validation example is not installed')
    f=cv2.imread(str(fixture))
    baseline=RipScoutModel().predict(f)
    result=LiveRipScoutModel().predict(f)
    assert baseline and result
    assert all(any(r['bbox_xyxy_px']==b['bbox_xyxy_px'] and r['score']==b['score']
                   and r['evidence_source']=='full_frame' for r in result) for b in baseline)
