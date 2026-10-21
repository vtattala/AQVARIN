import copy
import numpy as np
from vision.swimmer_identity import SwimmerIdentity

def swimmer(tid,box=(20,20,40,60)):
    return {'track_id':tid,'class':'swimmer','confidence':.8,'bbox_xyxy_px':list(box)}

def frame():
    return np.full((200,200,3),150,dtype=np.uint8)

def test_original_number_survives_two_new_tracker_ids_and_submersion():
    tracker=SwimmerIdentity(first_id=100)
    objects=[swimmer(11)]; saved=copy.deepcopy(objects)
    a=tracker.update(objects,frame(),0,0)[0]
    tracker.update([],frame(),1,.5)
    b=tracker.update([swimmer(49,(24,24,44,64))],frame(),30,1.2)[0]
    c=tracker.update([swimmer(211,(28,28,48,68))],frame(),60,2.4)[0]
    assert [a['track_id'],b['track_id'],c['track_id']]==[11,11,11]
    assert c['source_track_id']==211 and c['identity']['method']=='reacquired'
    assert c['track_age_frames']==61 and c['missed_frames']==29
    assert objects==saved

def test_nearby_swimmers_stay_separate_after_reappearance():
    tracker=SwimmerIdentity(first_id=100)
    a=tracker.update([swimmer(11),swimmer(12,(80,20,100,60))],frame(),0,0)
    b=tracker.update([swimmer(201,(24,20,44,60)),swimmer(202,(76,20,96,60))],frame(),60,2)
    assert [o['track_id'] for o in b]==[11,12]
    assert len({o['track_id'] for o in b})==2

def test_ambiguous_reappearance_is_not_forced_onto_either_person():
    tracker=SwimmerIdentity(first_id=100)
    tracker.update([swimmer(11),swimmer(12,(40,20,60,60))],frame(),0,0)
    o=tracker.update([swimmer(200,(30,20,50,60))],frame(),60,2)[0]
    assert o['track_id'] not in {11,12}
    assert o['identity']['method']=='new'

def test_scene_edit_and_long_absence_do_not_reuse_old_person():
    for cut,time in [(True,1),(False,9)]:
        tracker=SwimmerIdentity(first_id=100)
        tracker.update([swimmer(11)],frame(),0,0)
        o=tracker.update([swimmer(11)],frame(),100,time,cut)[0]
        assert o['track_id']!=11

def test_boats_and_scores_boxes_remain_unchanged():
    tracker=SwimmerIdentity(reserved_ids={2},first_id=100)
    boat={'track_id':2,'class':'boat','confidence':.9,'bbox_xyxy_px':[0,0,10,10]}
    person={**swimmer(11),'distress_action':{'label':'Active drowning','score':.91}}
    before=copy.deepcopy([boat,person])
    out=tracker.update(before,frame(),0,0)
    assert out[0]==boat
    assert out[1]['confidence']==person['confidence']
    assert out[1]['bbox_xyxy_px']==person['bbox_xyxy_px']
    assert out[1]['distress_action']==person['distress_action']
    assert before==[boat,person]

def test_appearance_prevents_swapped_source_ids_at_crossing():
    tracker=SwimmerIdentity(first_id=100)
    redgreen=frame();redgreen[20:60,20:40]=[0,0,255];redgreen[20:60,80:100]=[0,255,0]
    tracker.update([swimmer(11),swimmer(12,(80,20,100,60))],redgreen,0,0)
    # The original tracker swaps raw IDs; colors/positions support retaining people.
    out=tracker.update([swimmer(12),swimmer(11,(80,20,100,60))],redgreen,1,.03)
    assert [o['track_id'] for o in out]==[11,12]

def test_large_neighbor_box_cannot_steal_missing_swimmer_id():
    tracker=SwimmerIdentity(first_id=100)
    tracker.update([swimmer(11)],frame(),0,0)
    out=tracker.update([swimmer(28,(0,90,100,120))],frame(),30,1)[0]
    assert out['track_id']!=11


def test_reviewed_pool_geometry_keeps_drowner_through_rescue():
    tracker=SwimmerIdentity(first_id=250)
    image=np.full((1440,2304,3),150,dtype=np.uint8)
    trajectory=[(11,[1809,601,1937,749],0),(187,[1786,593,1984,807],1.82),
                (49,[1746,674,1944,768],2.96),(71,[1855,741,1959,817],3.78),
                (211,[1849,728,1986,819],3.93),(211,[1815,671,2080,862],8.15)]
    for i,(raw,box,now) in enumerate(trajectory):
        objects=[swimmer(raw,box)]
        if i==3:objects.append(swimmer(28,[1663,376,2175,555]))
        out=tracker.update(objects,image,i,now)
        assert out[0]['track_id']==11
        if len(out)>1:assert out[1]['track_id']!=11
