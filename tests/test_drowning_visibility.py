from vision.distress import DistressEngine, settings_from_file
from vision.action_yolo import VisibilityWatch, PersonTracks


def obj():
    return {'class':'swimmer','track_id':1,'confidence':.9,'center_px':[15,15],
            'bbox_xyxy_px':[10,10,20,20]}


def step(engine,t,score,token,label='Active drowning',cut=False):
    engine.update({'frame':round(t*30),'timestamp_s':t,'objects':[obj()],'scene_cut':cut},
                  [{'class':'drown','label':label,'score':score,'bbox_xyxy_px':[10,10,20,20],
                    'inference_timestamp_s':token}],action_ready=True)


def test_bursts_warn_using_unique_scores_not_continuous_frames():
    engine=DistressEngine(settings_from_file())
    step(engine,0,.72,0)
    step(engine,.12,.599901,.12)
    engine.update({'frame':7,'timestamp_s':.24,'objects':[]},action_ready=True)
    step(engine,.36,.86,.36)
    assert len(engine.events)==1
    event=engine.events[0]
    assert event['metrics']['distinct_predictions']==3
    assert abs(event['action_score']-(.72+.599901+.86)/3)<1e-8


def test_cached_frame_votes_never_create_warning():
    engine=DistressEngine(settings_from_file())
    for i in range(60): step(engine,i/30,.99,0)
    assert not engine.events


def test_scene_cuts_and_long_gaps_do_not_accumulate_votes():
    for cut in [True,False]:
        engine=DistressEngine(settings_from_file())
        step(engine,0,.9,0);step(engine,.12,.9,.12)
        step(engine,.3 if cut else 3,.9,3,cut=cut)
        assert not engine.events


def test_low_scores_and_confident_swimming_do_not_warn():
    engine=DistressEngine(settings_from_file())
    for i in range(10):step(engine,i/10,.65,i/10)
    assert not engine.events
    engine=DistressEngine(settings_from_file())
    step(engine,0,.9,0);step(engine,.1,.9,.1)
    engine.update({'frame':6,'timestamp_s':.2,'objects':[obj()]},
                  [{'class':'swim','label':'Swimming','score':.9,'bbox_xyxy_px':[10,10,20,20]}],action_ready=True)
    step(engine,.3,.9,.3)
    assert not engine.events


def test_missing_swimmer_is_not_fabricated_detection_or_score():
    watch=VisibilityWatch()
    assert not watch.update([obj()],0)
    lost=watch.update([],.4)
    assert lost[0]['confidence'] is None and lost[0]['action_score'] is None
    assert lost[0]['bbox_xyxy_px']==obj()['bbox_xyxy_px']
    assert watch.rois(.5)
    assert not watch.update([],1.6)


def test_visibility_resets_on_scene_change_and_reappearance():
    watch=VisibilityWatch();watch.update([obj()],0)
    assert not watch.update([obj()],.4)
    assert not watch.update([],.5,True)
    watch.update([obj()],1)
    other=dict(obj(),track_id=2)
    assert not watch.update([other],1.3)


def test_companion_identity_recovers_across_brief_gap():
    tracker=PersonTracks(100)
    p={'bbox_xyxy_px':[10,10,20,20],'score':.9}
    a=tracker.update([p],0,0)[0]
    tracker.update([],1,.4)
    b=tracker.update([p],2,1.1)[0]
    assert a['track_id']==b['track_id']


def test_crop_only_noise_and_passive_resting_need_stronger_evidence():
    engine=DistressEngine(settings_from_file())
    for i in range(10):
        p={'class':'drown','label':'Active drowning','score':.85,'bbox_xyxy_px':[10,10,20,20],
           'crop_track_id':1,'inference_timestamp_s':i/10}
        engine.update({'frame':i,'timestamp_s':i/10,'objects':[obj()]},[p],action_ready=True)
    assert not engine.events
    engine=DistressEngine(settings_from_file())
    for i in range(10):step(engine,i/10,.85,i/10,'Possible Passive Drowner')
    assert not engine.events
