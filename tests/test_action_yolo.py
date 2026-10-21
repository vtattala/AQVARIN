import copy
import json
import pytest
from vision.action_yolo import PersonTracks, reconcile, ActionModels, filter_actions
from vision.distress import DistressEngine, settings_from_file


def object_(tid, label, box):
    return {'track_id':tid,'class':label,'class_id':4 if label=='swimmer' else 0,
            'bbox_xyxy_px':box,'confidence':.8}


def prediction(label, box, score=.9):
    return {'class':'swim' if label=='Swimming' else 'drown','label':label,'bbox_xyxy_px':box,'score':score}


def test_supported_person_correction_preserves_primary_swimmer_and_true_boat():
    objects = [object_(1,'swimmer',[0,0,10,10]),object_(2,'boat',[40,40,60,60]),object_(3,'boat',[100,100,120,120])]
    saved = copy.deepcopy(objects)
    action = [prediction('Swimming',[40,40,60,60])]
    humans = [{'score':.8,'bbox_xyxy_px':[40,40,60,60]}]
    kept,audit = reconcile(objects,action,humans,[],[object_(10,'swimmer',[40,40,60,60])])
    assert kept == [objects[0],objects[2],object_(10,'swimmer',[40,40,60,60])]
    assert len(audit) == 1
    assert objects == saved


def test_person_on_confirmed_boat_does_not_remove_boat():
    objects = [object_(1,'boat',[0,0,100,100])]
    p = prediction('Swimming',[0,0,100,100])
    kept,audit = reconcile(objects,[p],[],[{'bbox_xyxy_px':[0,0,100,100],'score':.9}],[])
    assert kept == objects and not audit


def test_no_boat_reference_constraint_is_explicit():
    objects = [object_(1,'swimmer',[0,0,10,10]),object_(2,'boat',[40,40,60,60])]
    kept,audit = reconcile(objects,[],[],[],[],allow_boats=False)
    assert kept == [objects[0]] and 'exact source hash' in audit[0]['reason']
    assert reconcile(objects,[],[],[],[])[0] == objects


def test_single_action_model_cannot_remove_a_primary_boat():
    objects = [object_(1,'boat',[40,40,60,60])]
    p = prediction('Swimming',[40,40,60,60])
    assert reconcile(objects,[p],[],[],[])[0] == objects


def test_reviewed_people_only_clip_rejects_other_maritime_classes():
    objects = [object_(1,'swimmer',[0,0,10,10]),object_(2,'jetski',[40,40,60,60])]
    assert reconcile(objects,[],[],[],[],allowed_classes=['swimmer'])[0] == [objects[0]]


def test_oversized_panel_is_not_a_swimmer_and_supported_person_is_kept():
    p = prediction('Possible Passive Drowner',[0,0,500,400])
    assert filter_actions([p],[],[],[],1000,1000)[0] == []
    humans = [{'bbox_xyxy_px':[0,0,500,400],'score':.8}]
    assert filter_actions([p],[],humans,[],1000,1000)[0] == [p]


def test_action_on_verified_hull_is_rejected():
    p = prediction('Active drowning',[10,10,30,30])
    boats = [{'bbox_xyxy_px':[0,0,100,100],'score':.8}]
    assert filter_actions([p],[],[],boats,1000,1000)[0] == []


def test_additional_person_identity_continues_and_does_not_duplicate_primary():
    tracker = PersonTracks(100)
    p = prediction('Swimming',[10,10,30,30])
    a = tracker.update([p],0,0)[0]
    b = tracker.update([p],1,.03)[0]
    assert a['track_id'] == b['track_id'] == 100
    assert b['track_age_frames'] == 2
    kept,_ = reconcile([object_(1,'swimmer',[10,10,30,30])],[p],[],[],[b])
    assert len(kept) == 1


def test_single_frame_action_does_not_create_warning_and_cut_resets_evidence():
    engine = DistressEngine(settings_from_file())
    p = prediction('Active drowning',[0,0,10,10])
    objects = [dict(object_(1,'swimmer',[0,0,10,10]),center_px=[5,5])]
    for i in range(20):
        engine.update({'frame':i,'timestamp_s':i/10,'objects':objects},[p],action_ready=True)
    assert not engine.events
    engine.update({'frame':20,'timestamp_s':2,'objects':objects,'scene_cut':True},[p],action_ready=True)
    assert not engine.events


def test_packaged_checkpoint_is_real_and_classes_match():
    models = ActionModels()
    try:
        assert models.action.names == {0:'Active drowning',1:'Possible Passive Drowner',2:'Swimming'}
    finally:
        models.close()


def test_action_detection_on_supplied_validation_example():
    import os
    if os.environ.get('RUN_VIDEO_TEST') != '1':
        pytest.skip('Set RUN_VIDEO_TEST=1 for actual trained-model inference')
    import cv2
    from vision.config import ROOT
    from vision.distress import box_iou
    images = sorted((ROOT/'third_party/drowning-detection-system/data/test/images').glob('*.jpg'))
    if not images:
        pytest.skip('Upstream evaluation images are not checked out')
    models = ActionModels()
    try:
        # A labeled positive must yield a real action proposal, not just successful loading.
        hit = False
        for path in images[:12]:
            frame = cv2.imread(str(path))
            assert frame is not None
            expected = []
            for row in (path.parent.parent/'labels'/path.with_suffix('.txt').name).read_text().splitlines():
                cls,x,y,w,h = map(float,row.split())
                if cls in {0,1}:
                    expected.append(((x-w/2)*frame.shape[1],(y-h/2)*frame.shape[0],
                                     (x+w/2)*frame.shape[1],(y+h/2)*frame.shape[0]))
            result = models.action.predict(frame,conf=.25,imgsz=640,device='cpu',verbose=False)[0]
            if any(int(b.cls.item()) in {0,1} and any(box_iou(b.xyxy[0].tolist(),e) >= .4 for e in expected) for b in result.boxes):
                hit = True
                break
        assert hit
    finally:
        models.close()


def test_saved_boat_conflicts_require_independent_person_evidence():
    """Regression for yacht boxes that the action model alone called people."""
    from vision.config import ROOT
    path = ROOT/'outputs/yachts_actions.audit.jsonl'
    if not path.exists():
        pytest.skip('Run the yacht reference analysis to create the regression fixture')
    for line in path.read_text().splitlines():
        for item in json.loads(line)['suppressed']:
            obj = item['object']
            p = prediction('Swimming',obj['bbox_xyxy_px'])
            assert reconcile([obj],[p],[],[],[])[0] == [obj]
