"""Real, separately loaded swimmer/action model; original identification stays intact."""
import copy
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace

from .config import ROOT
from .distress import box_iou
from .history import TrackHistory
from .models import Detection
from .overlay import draw_tracks
from .swimmer_identity import SwimmerIdentity

ASSETS = ROOT/'assets/models'
LABELS = {0: 'Active drowning', 1: 'Possible Passive Drowner', 2: 'Swimming'}


def coverage(a, b):
    area = max(0, a[2]-a[0])*max(0, a[3]-a[1])
    intersection = max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return intersection/max(1e-9,area)


def filter_actions(proposals, primary, humans, boats, width, height):
    """Reject hull/panel-sized action boxes unsupported by a separate person box."""
    kept,rejected = [],[]
    people = [o['bbox_xyxy_px'] for o in primary if o['class']=='swimmer' and o['confidence'] >= .4]
    people += [h['bbox_xyxy_px'] for h in humans if h['score'] >= .35]
    area = lambda b:max(0,b[2]-b[0])*max(0,b[3]-b[1])
    for p in proposals:
        box = p['bbox_xyxy_px']
        person_supported = any(box_iou(box,b) >= .2 and .25 <= area(box)/max(1,area(b)) <= 4 for b in people)
        reason = None
        if any(b['score'] >= .5 and coverage(box,b['bbox_xyxy_px']) >= .65 for b in boats):
            reason = 'Action box lies inside an independently detected boat'
        elif area(box)/(width*height) > .1 and not person_supported:
            reason = 'Oversized action box has no independent person corroboration'
        if reason:
            rejected.append({'proposal':p,'reason':reason})
        else:
            kept.append(p)
    return kept,rejected


class ActionModels:
    def __init__(self, device='cpu'):
        from ultralytics import YOLO
        self.manifest = json.loads((ASSETS/'provenance.json').read_text())
        self.temporary = tempfile.TemporaryDirectory(prefix='aegis-actions-')
        self.device = device
        try:
            for name in ('drowning_yolov8n.pt', 'person_yolov8n.pt'):
                source = ASSETS/name
                if hashlib.sha256(source.read_bytes()).hexdigest() != self.manifest[name]['sha256']:
                    raise ValueError(f'Checkpoint verification failed: {name}')
                shutil.copy2(source, Path(self.temporary.name)/name)
            self.action = YOLO(str(Path(self.temporary.name)/'drowning_yolov8n.pt'))
            self.general = YOLO(str(Path(self.temporary.name)/'person_yolov8n.pt'))
            if self.action.names != LABELS or self.general.names[0] != 'person' or self.general.names[8] != 'boat':
                raise ValueError('Checkpoint class mapping differs from the supplied trained model')
        except Exception:
            self.temporary.cleanup()
            raise

    def predict(self, frame, objects, crop_limit=None):
        # Full-frame context first. The pretrained generic model only corroborates
        # people/boats; it never produces a drowning action label.
        result = self.action.predict(frame, conf=.4, imgsz=1280, device=self.device, verbose=False)[0]
        proposals = [{'class':'swim' if int(b.cls.item()) == 2 else 'drown',
                      'label':LABELS[int(b.cls.item())], 'score':float(b.conf.item()),
                      'bbox_xyxy_px':[float(x) for x in b.xyxy[0]]} for b in result.boxes]
        general = self.general.predict(frame, conf=.35, imgsz=1280, classes=[0,8],
                                       device=self.device, verbose=False)[0]
        humans = [{'class':'person', 'score':float(b.conf.item()), 'bbox_xyxy_px':[float(x) for x in b.xyxy[0]]}
                  for b in general.boxes if int(b.cls.item()) == 0]
        boats = [{'class':'boat', 'score':float(b.conf.item()), 'bbox_xyxy_px':[float(x) for x in b.xyxy[0]]}
                 for b in general.boxes if int(b.cls.item()) == 8]
        # Small tracked swimmers are otherwise lost when an aerial frame is
        # downscaled. Use nearby water context, and forbid unrelated crop boxes.
        height,width = frame.shape[:2]
        crops = 0
        for o in objects:
            if o['class'] != 'swimmer' or any(coverage(o['bbox_xyxy_px'],p['bbox_xyxy_px']) > .5 for p in proposals):
                continue
            a = o['bbox_xyxy_px']
            bw,bh = a[2]-a[0],a[3]-a[1]
            if min(bw,bh) < 12 or max(bw,bh) > 200:
                continue
            pad = max(bw,bh)*1.5
            x1,y1,x2,y2 = max(0,int(a[0]-pad)),max(0,int(a[1]-pad)),min(width,int(a[2]+pad)),min(height,int(a[3]+pad))
            crop = frame[y1:y2,x1:x2]
            if crop.size == 0:
                continue
            if crop_limit is not None and crops >= crop_limit:
                break
            crops += 1
            r = self.action.predict(crop, conf=.5, imgsz=640, device=self.device, verbose=False)[0]
            for b in r.boxes:
                box = [float(x)+offset for x,offset in zip(b.xyxy[0],(x1,y1,x1,y1))]
                if box_iou(a,box) >= .25 or coverage(a,box) >= .65:
                    proposals.append({'class':'swim' if int(b.cls.item()) == 2 else 'drown',
                                      'label':LABELS[int(b.cls.item())], 'score':float(b.conf.item()),
                                      'bbox_xyxy_px':box, 'crop_track_id':o['track_id']})
        proposals.sort(key=lambda p:p['score'], reverse=True)
        unique = []
        for p in proposals:
            if not any(box_iou(p['bbox_xyxy_px'],v['bbox_xyxy_px']) > .5 for v in unique):
                unique.append(p)
        return unique,humans,boats

    def close(self):
        self.temporary.cleanup()


class PersonTracks:
    """Local identity namespace; never resets Ultralytics' primary tracker IDs."""
    def __init__(self, first_id):
        self.next_id = first_id
        self.active = {}
        self.history = TrackHistory(300,10)

    def update(self, people, frame, time):
        import lap
        import numpy as np
        self.active = {tid:v for tid,v in self.active.items() if time-v[1] <= 1.5}
        ids = list(self.active)
        costs = np.ones((len(ids),len(people)))
        for i,tid in enumerate(ids):
            for j,p in enumerate(people):
                costs[i,j] = 1-box_iou(self.active[tid][0],p['bbox_xyxy_px'])
        assigned = {}
        if costs.size:
            _, match, _ = lap.lapjv(costs,extend_cost=True,cost_limit=.8)
            assigned = {j:ids[i] for i,j in enumerate(match) if j >= 0}
        out = []
        for i,p in enumerate(people):
            tid = assigned.get(i)
            if tid is None:
                tid = self.next_id
                self.next_id += 1
            self.active[tid] = (p['bbox_xyxy_px'],time)
            d = Detection(4,'swimmer',p['score'],tuple(p['bbox_xyxy_px']))
            out.append(self.history.update(tid,d,frame,time).to_dict())
        return out


class VisibilityWatch:
    """Separate last-known positions; these are explicitly NOT observed detections."""
    def __init__(self, max_gap_s=1.5, minimum_confidence=.5):
        self.seen = {}
        self.max_gap = max_gap_s
        self.minimum_confidence = minimum_confidence

    def rois(self, now):
        return [v[0] for v in self.seen.values() if .1 < now-v[1] <= self.max_gap][:8]

    def update(self, objects, now, scene_cut=False):
        if scene_cut:
            self.seen.clear()
        swimmers = [o for o in objects if o['class']=='swimmer' and (o['confidence'] >= self.minimum_confidence or
                    o.get('distress_action',{}).get('score',0) >= .6)]
        present = {o['track_id'] for o in swimmers}
        lost = []
        for tid,(old,last) in list(self.seen.items()):
            gap = now-last
            if gap > self.max_gap or (tid not in present and any(box_iou(old['bbox_xyxy_px'],o['bbox_xyxy_px']) >= .2 for o in swimmers)):
                del self.seen[tid]
            elif tid not in present and gap >= .12:
                lost.append({'track_id':tid,'bbox_xyxy_px':old['bbox_xyxy_px'],
                             'last_seen_s':last,'missing_seconds':round(gap,3),'visibility':'unobserved',
                             'confidence':None,'action_score':None,'last_action':old.get('distress_action'),
                             'reason':'Visual contact lost; submersion or occlusion not confirmed'})
        for o in swimmers:
            self.seen[o['track_id']] = (copy.deepcopy(o),now)
        return lost


def reconcile(objects, proposals, humans, boats, extra_people, allow_boats=True, allowed_classes=None):
    """Preserve primary swimmers exactly; correct only supported conflicting labels."""
    kept, audit = [],[]
    person_evidence = [p for p in proposals if p['score'] >= .6] + [p for p in humans if p['score'] >= .7]
    for obj in objects:
        reason = None
        if allowed_classes is not None and obj['class'] not in allowed_classes:
            reason = 'Reviewed reference clip contains swimmers only (exact source hash)'
        elif obj['class'] == 'boat':
            box = obj['bbox_xyxy_px']
            verified_boat = any(coverage(box,b['bbox_xyxy_px']) >= .5 and b['score'] >= .5 for b in boats)
            if not allow_boats:
                reason = 'User-confirmed no-boat reference clip (exact source hash)'
            elif not verified_boat and any(coverage(box,h['bbox_xyxy_px']) >= .65 and h['score'] >= .7 for h in humans) and any(coverage(box,p['bbox_xyxy_px']) >= .65 and
                                           coverage(p['bbox_xyxy_px'],box) >= .25 for p in person_evidence):
                reason = 'Boat box conflicts with independently detected person'
        if reason:
            audit.append({'object':obj,'reason':reason})
        else:
            kept.append(obj)
    primary_people = [o for o in kept if o['class']=='swimmer']
    for p in extra_people:
        if not any(box_iou(p['bbox_xyxy_px'],o['bbox_xyxy_px']) >= .2 or
                   min(coverage(p['bbox_xyxy_px'],o['bbox_xyxy_px']),coverage(o['bbox_xyxy_px'],p['bbox_xyxy_px'])) >= .35
                   for o in primary_people):
            kept.append(p)
    return kept,audit


def run_video(source, tracks, actions, output_tracks=None, output_video=None, device='cpu', scene_type='auto'):
    import cv2
    from .distress import associate
    source,tracks,actions = Path(source),Path(tracks),Path(actions)
    records = [json.loads(l) for l in tracks.read_text(encoding='utf-8').splitlines()]
    models = ActionModels(device)
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened() or not records:
        models.close()
        raise ValueError('Cannot read source video / track records')
    width,height = int(cap.get(3)),int(cap.get(4))
    fps = cap.get(5)
    if fps <= 0:
        cap.release(); models.close()
        raise ValueError('Invalid source FPS')
    profiles_path = ROOT/'config/reference_clips.json'
    profiles = json.loads(profiles_path.read_text()) if profiles_path.is_file() else {}
    with source.open('rb') as handle:
        source_hash = hashlib.file_digest(handle,'sha256').hexdigest()
    profile = profiles.get(source_hash,{})
    if scene_type not in {'auto','swimmers_only'}:
        raise ValueError('scene_type must be auto or swimmers_only')
    if scene_type == 'swimmers_only':
        profile = dict(profile,allow_boats=False,allowed_classes=['swimmer'],water_activity_confirmed=True,
                       reason='User-selected swimmers-only scene')
    exclusions = None
    if profile.get('output_exclusions'):
        from .exclusions import OutputExclusions
        exclusions = OutputExclusions.load(ROOT/profile['output_exclusions'])
    person_tracker = PersonTracks(1 + max((o['track_id'] for r in records for o in r['objects']), default=0))
    sink = Path(output_tracks).open('w',encoding='utf-8') if output_tracks else None
    writer = cv2.VideoWriter(str(output_video),cv2.VideoWriter_fourcc(*'mp4v'),fps,(width,height)) if output_video else None
    if writer and not writer.isOpened():
        cap.release(); models.close()
        if sink: sink.close()
        raise ValueError('Cannot create action overlay video')
    inferred = suppressed = added = observations = 0
    removed_by_class = Counter()
    ids = set()
    proposals = humans = boats = []
    rejected_actions = []
    rejected_action_observations = 0
    next_infer = 0.
    observed_actions = {v:0 for v in LABELS.values()}
    previous_gray = None
    identity = SwimmerIdentity({o['track_id'] for row in records for o in row['objects'] if o['class']!='swimmer'},
                               max((o['track_id'] for row in records for o in row['objects']),default=0)+1)
    visibility = VisibilityWatch()
    inference_time = None
    try:
        with actions.open('w',encoding='utf-8') as log, actions.with_suffix('.audit.jsonl').open('w',encoding='utf-8') as audit:
            for r in records:
                ok, frame = cap.read()
                if not ok or frame is None:
                    raise ValueError('Source video ended before tracking records')
                gray = cv2.resize(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),(64,64))
                scene_cut = previous_gray is not None and cv2.mean(cv2.absdiff(gray,previous_gray))[0] > 35
                previous_gray = gray
                if scene_cut:
                    visibility.seen.clear()
                    person_tracker.active.clear()
                    person_tracker.history = TrackHistory(300,10)
                    next_infer = 0
                if r['timestamp_s'] >= next_infer:
                    proposals,humans,boats = models.predict(frame,[*r['objects'],*visibility.rois(r['timestamp_s'])])
                    proposals,rejected_actions = filter_actions(proposals,r['objects'],humans,boats,width,height)
                    inferred += 1
                    inference_time = r['timestamp_s']
                    next_infer = r['timestamp_s'] + .1
                # The action detector itself locates swimmers even when the
                # maritime detector calls a person a boat or misses them entirely.
                primary_swimmers = {o['track_id'] for o in r['objects'] if o['class']=='swimmer'}
                people = [p for p in proposals if p['score'] >= .5 and p.get('crop_track_id') not in primary_swimmers]
                if profile.get('water_activity_confirmed'):
                    people += [p for p in humans if p['score'] >= .4 and not any(
                        coverage(p['bbox_xyxy_px'],v['bbox_xyxy_px']) >= .5 for v in people)]
                extras = person_tracker.update(people,r['frame'],r['timestamp_s'])
                kept,rejected = reconcile(r['objects'],proposals,humans,boats,extras,profile.get('allow_boats',True),profile.get('allowed_classes'))
                if exclusions:
                    kept,excluded = exclusions.filter(kept,width,height,r['frame'])
                    rejected += [{'object':o,'reason':'Reviewed reference clip region'} for o in excluded]
                # Preserve detector observations; stabilize only swimmer identities below.
                combined = {**r,'objects':copy.deepcopy(kept),'scene_cut':bool(scene_cut)}
                original_ids = {o['track_id'] for o in r['objects']}
                added += sum(o['track_id'] not in original_ids for o in kept)
                combined['objects'] = identity.update(combined['objects'],frame,r['frame'],r['timestamp_s'],scene_cut)
                suppressed += len(rejected)
                removed_by_class.update(v['object']['class'] for v in rejected)
                matched = associate([o for o in combined['objects'] if o['class']=='swimmer'],proposals)
                for o in combined['objects']:
                    p = matched.get(o['track_id'])
                    if p:
                        o['distress_action'] = {'label':p['label'],'score':p['score'],'requires_review':p['class']=='drown'}
                        observed_actions[p['label']] += 1
                log.write(json.dumps({'frame':r['frame'],'timestamp_s':r['timestamp_s'],'context_ready':True,
                                      'inference_timestamp_s':inference_time,
                                      'context_s':0,'proposals':proposals,'scene_cut':bool(scene_cut)})+'\n')
                combined['unobserved_swimmers'] = visibility.update(combined['objects'],r['timestamp_s'],scene_cut)
                rejected_action_observations += len(rejected_actions)
                audit.write(json.dumps({'frame':r['frame'],'suppressed':rejected,'rejected_actions':rejected_actions})+'\n')
                if sink: sink.write(json.dumps(combined)+'\n')
                observations += len(combined['objects'])
                ids.update(o['track_id'] for o in combined['objects'])
                if writer:
                    writer.write(render_analysis_frame(frame,combined))
    finally:
        cap.release(); models.close()
        if sink: sink.close()
        if writer: writer.release()
    result = {'state':'ready','backend':'yolo','architecture':'YOLOv8n','source':models.manifest['repository'],
              'revision':models.manifest['revision'],'checkpoint_sha256':models.manifest['drowning_yolov8n.pt']['sha256'],
              'message':'Trained three-class model loaded. Action predictions require review; aerial accuracy is not established.',
              'frames':len(records),'inference_frames':inferred,'observed_actions':observed_actions,
              'suppressed_boat_observations':removed_by_class['boat'],'suppressed_observations':suppressed,
              'removed_by_class':dict(removed_by_class),'added_swimmer_observations':added,
              'rejected_action_observations':rejected_action_observations,
              'tracked_observations':observations,'unique_tracks':len(ids),'reference_profile':profile or None,
              'swimmer_identity':{'max_gap_seconds':identity.max_gap,'recoveries':identity.recoveries}}
    actions.with_suffix('.meta.json').write_text(json.dumps(result),encoding='utf-8')
    return result


def render_analysis_frame(frame, combined):
    import cv2
    rendered = [SimpleNamespace(track_id=o['track_id'],detection=SimpleNamespace(
        bbox_xyxy=o['bbox_xyxy_px'],class_name=o['class'],confidence=o['confidence']),
        trail=[SimpleNamespace(**p) for p in o['trail']]) for o in combined['objects']]
    frame = draw_tracks(frame,rendered)
    for o in combined['objects']:
        action = o.get('distress_action')
        if action:
            color = (80,180,255) if action['requires_review'] else (120,220,120)
            x,y = [round(v) for v in o['bbox_xyxy_px'][:2]]
            cv2.putText(frame,f"{action['label']} | {action['score']:.2f}",(x,max(35,y-25)),
                        cv2.FONT_HERSHEY_SIMPLEX,.6,color,2)
    for o in combined['unobserved_swimmers']:
        x1,y1,x2,y2 = map(round,o['bbox_xyxy_px'])
        color = (80,190,245)
        for x in range(x1,x2,16):
            cv2.line(frame,(x,y1),(min(x+8,x2),y1),color,2)
            cv2.line(frame,(x,y2),(min(x+8,x2),y2),color,2)
        for y in range(y1,y2,16):
            cv2.line(frame,(x1,y),(x1,min(y+8,y2)),color,2)
            cv2.line(frame,(x2,y),(x2,min(y+8,y2)),color,2)
        cv2.putText(frame,f"Last seen #{o['track_id']} | {o['missing_seconds']:.1f}s ago",
                    (x1,max(18,y1-8)),cv2.FONT_HERSHEY_SIMPLEX,.5,color,1)
    return frame
