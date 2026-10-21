"""Stateful, memory-only camera analysis. No video jobs or shared tracker state.

One frame in flight per session: clients capture AFTER the preceding response.
The returned JPEG is the exact frame analyzed, not boxes painted on a newer image.
"""
import base64
import io
import math
import time
import multiprocessing
import copy
from collections import deque
from threading import Lock
from uuid import uuid4

import cv2
import numpy as np
from PIL import Image
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .action_yolo import ActionModels, PersonTracks, VisibilityWatch, filter_actions, reconcile, render_analysis_frame
from .config import PipelineConfig
from .detector import MaritimeDetector
from .distress import DistressEngine, associate, box_iou, settings_from_file
from .history import TrackHistory
from .live_rip import LiveRipScoutModel, LiveRipEvidence
from .swimmer_identity import SwimmerIdentity
from .live_runtime import activate_live_runtime
from .live_actions import LiveActionModels

MAX_BYTES = 2_000_000
IDLE_SECONDS = 120
MAX_SESSION_SECONDS = 3600
router = APIRouter(prefix='/api/live')


class LiveSwimmerIdentity(SwimmerIdentity):
    """Odd swimmer IDs and even other-object IDs cannot collide mid-stream."""
    def allocate(self):
        while self.next_id in self.used:
            self.next_id += 2
        value = self.next_id
        self.next_id += 2
        return value


class LiveVisibilityWatch(VisibilityWatch):
    """Retain threatened swimmers longer and prioritize their search crops."""
    def __init__(self):
        super().__init__(max_gap_s=8,minimum_confidence=.1)

    def rois(self,now):
        candidates = [v[0] for v in self.seen.values() if .1 < now-v[1] <= 3]
        candidates.sort(key=lambda o: -(o.get('distress_action') or o.get('last_known_action') or {}).get('score',0)
                        if (o.get('distress_action') or o.get('last_known_action') or {}).get('requires_review') else 0)
        return candidates[:8]

    def update(self,objects,now,scene_cut=False):
        previous = {} if scene_cut else {tid:old.get('distress_action') or old.get('last_known_action')
                                        for tid,(old,_) in self.seen.items()}
        lost = super().update(objects,now,scene_cut)
        for tid,(old,last) in list(self.seen.items()):
            action = old.get('distress_action') or previous.get(tid)
            if action:
                old['last_known_action'] = action
            if now-last > 3 and not (action or {}).get('requires_review'):
                del self.seen[tid]
        for marker in lost:
            marker['last_action'] = marker['last_action'] or previous.get(marker['track_id'])
        return [marker for marker in lost if marker['track_id'] in self.seen]


def warn_on_lost_distress(engine,record):
    """Two strong, independent full-frame action observations plus contact loss.

    Contact loss is an additional review signal, never a fabricated underwater
    detection or a third neural vote. Camera/network gaps and cuts cannot vote.
    """
    now = record['timestamp_s']
    if record.get('scene_cut'):
        return
    for lost in record['unobserved_swimmers']:
        tid = lost['track_id']
        if not .75 <= lost['missing_seconds'] <= 3 or now-engine.last_alert.get(tid,-math.inf) < 10:
            continue
        support = [v for v in engine.action_windows.get(tid,())
                   if now-v[0] <= 4 and v[2].get('label')=='Active drowning'
                   and v[2]['score'] >= .65 and 'crop_track_id' not in v[2]]
        if (len(support)<2 or support[-1][0]-support[0][0] < .2-1e-6
                or max(v[2]['score'] for v in support)<.8
                or lost['last_seen_s']-support[-1][0]>2):
            continue
        engine.events.append({'track_id':tid,'frame':record['frame'],'timestamp_s':now,
                              'start_s':support[0][0],'type':'possible_distress','requires_review':True,
                              'signals':['active_drowning','visual_contact_lost'],
                              'metrics':{'distinct_predictions':len(support),'peak_action_score':max(v[2]['score'] for v in support),
                                         'evidence_span_seconds':support[-1][0]-support[0][0],
                                         'last_seen_s':lost['last_seen_s'],'missing_seconds':lost['missing_seconds']},
                              'action_score':sum(v[2]['score'] for v in support)/len(support),
                              'score_basis':'mean of distinct supporting model predictions; contact loss is a separate signal'})
        engine.last_alert[tid] = now


class LiveTracks:
    """Class-aware frame association without Ultralytics' global ID counter.

    Hungarian IoU matching keeps non-swimmer IDs; the existing appearance and
    camera-compensated swimmer identity layer handles swimmer reacquisition.
    """
    def __init__(self):
        self.active = {}
        self.next_id = 1
        self.history = TrackHistory(60,10)

    def update(self, detections, frame_number, now):
        import lap
        self.active = {k:v for k,v in self.active.items() if now-v[1] <= 2}
        ids = list(self.active)
        assigned = {}
        # Match confident detections first, then use low-confidence observations
        # only to continue existing tracks (the upload tracker's two thresholds).
        for candidates in ([j for j,d in enumerate(detections) if d.confidence >= .3],
                           [j for j,d in enumerate(detections) if .1 <= d.confidence < .3]):
            remaining = [tid for tid in ids if tid not in assigned.values()]
            costs = np.full((len(remaining),len(candidates)),100.)
            for i,tid in enumerate(remaining):
                old, _ = self.active[tid]
                for k,j in enumerate(candidates):
                    if old.class_name == detections[j].class_name:
                        costs[i,k] = 1-box_iou(old.bbox_xyxy,detections[j].bbox_xyxy)
            if costs.size:
                _,matches,_ = lap.lapjv(costs,extend_cost=True,cost_limit=.8)
                assigned.update({candidates[k]:remaining[i] for i,k in enumerate(matches) if k >= 0})
        objects = []
        for j,detection in enumerate(detections):
            tid = assigned.get(j)
            if tid is None:
                if detection.confidence < .3:
                    continue
                tid = self.next_id
                self.next_id += 1
            self.active[tid] = (detection,now)
            raw_id = tid*2+(1 if detection.class_name == 'swimmer' else 0)
            objects.append(self.history.update(raw_id,detection,frame_number,now).to_dict())
        return objects


def recover_known_swimmers(humans, primary, remembered, now):
    """Person detections may recover a known swimmer, never establish water context.

    Require an unambiguous spatial match within three seconds. A completely
    invisible swimmer remains in the separate unobserved list.
    """
    candidates = []
    for human in humans:
        if human['score'] < .4:
            continue
        box = human['bbox_xyxy_px']
        if any(o['class']=='swimmer' and box_iou(box,o['bbox_xyxy_px']) >= .2 for o in primary):
            continue
        ranked = sorted([(box_iou(box,t['box']),tid) for tid,t in remembered.items()
                         if now-t['time'] <= 3],reverse=True)
        if not ranked or ranked[0][0] < .3 or (len(ranked)>1 and ranked[0][0]-ranked[1][0] < .15):
            continue
        candidates.append((ranked[0][0],ranked[0][1],human))
    used = set()
    recovered = []
    for _,tid,human in sorted(candidates,key=lambda v:v[0],reverse=True):
        if tid in used:
            continue
        used.add(tid)
        recovered.append(human)
    return recovered


def decode_camera_frame(data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Send a JPEG frame smaller than 2 MB')
    # Inspect dimensions before decompression; cap memory even for malformed input.
    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'JPEG' or min(image.size) < 64 or max(image.size) > 2560 or image.width*image.height > 4_000_000:
            raise ValueError('Camera frame must be JPEG, 64–2560 px, at most 4 megapixels')
    frame = cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError('JPEG frame could not be decoded')
    return frame


def prune_history(history, now):
    expired = [tid for tid,points in history._points.items() if not points or now-points[-1].timestamp_s > 10]
    for tid in expired:
        for field in ('_points','_first_frame','_last_frame','_consecutive'):
            getattr(history,field).pop(tid,None)


class LiveEngine:
    def __init__(self, scene_type='auto', detector=None, actions=None, rip=None):
        self.scene_type = scene_type
        self.detector = detector or MaritimeDetector(PipelineConfig(confidence=.1))
        self.models = {'identification':{'state':'ready','device':str(self.detector.device)}}
        self.actions = actions
        self.rip = rip
        if self.actions is None:
            try:
                self.actions = LiveActionModels(self.detector.device)
            except Exception as exc:
                self.models['drowning'] = {'state':'failed','message':str(exc)}
        if self.rip is None:
            try:
                self.rip = LiveRipScoutModel()
            except Exception as exc:
                self.models['rip_current'] = {'state':'failed','message':str(exc)}
        if self.actions is not None: self.models['drowning'] = {'state':'ready','source':getattr(self.actions,'model_source','imported_checkpoint')}
        if self.rip is not None: self.models['rip_current'] = {'state':'ready','label':'sediment_rip',
            'labels':['sediment_rip'], 'scope':'visible sediment-plume candidates',
            'search':'original checkpoint; full frame + bounded context crops'}
        self.tracks = LiveTracks()
        self.people = PersonTracks(1_000_000)
        self.identity = LiveSwimmerIdentity(first_id=1)
        self.visibility = LiveVisibilityWatch()
        # Use the existing calibrated warning rules, never infer camera calibration.
        self.distress = DistressEngine(dict(settings_from_file(),backend='yolo',motion_reference='uncalibrated',water_confirmed=False,
                                           action_window_seconds=6,action_memory_seconds=6,
                                           minimum_swimmer_confidence=.1))
        self.rip_evidence = LiveRipEvidence()
        self.previous_gray = None
        self.shape = None
        self.index = 0
        self.last_time = -1.
        self.crop_cursor = 0
        self.review_candidates = {}

    def process(self, frame, timestamp, sequence):
        started = time.perf_counter()
        if timestamp <= self.last_time:
            raise ValueError('Frame timestamp must increase')
        gray = cv2.resize(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),(64,64))
        sample_gap = timestamp-self.last_time if self.last_time >= 0 else None
        gap = sample_gap is not None and sample_gap > 2.5
        cut = gap or (self.shape is not None and self.shape != frame.shape) or (
            self.previous_gray is not None and cv2.mean(cv2.absdiff(gray,self.previous_gray))[0] > 35)
        self.previous_gray, self.shape = gray, frame.shape
        self.last_time = timestamp
        if cut:
            self.tracks.active.clear()
            self.people.active.clear()
            self.rip_evidence.tracks.clear()
            if self.rip is not None and hasattr(self.rip,'reset'):
                self.rip.reset()
        detections,detector_ms = self.detector.detect(frame)
        primary = self.tracks.update(detections,self.index,timestamp)
        proposals, humans, boats = [],[],[]
        rejected_actions = []
        action_start = time.perf_counter()
        if self.actions is not None:
            try:
                if isinstance(self.actions,ActionModels):
                    # Full-frame inference remains unchanged. Bound extra crop work
                    # so crowded live feeds do not accumulate multi-second delays.
                    # Rotate the remaining swimmers to avoid starving later tracks.
                    offset = self.crop_cursor % max(1,len(primary))
                    rotated = primary[offset:]+primary[:offset]
                    priority = [o for o in self.visibility.rois(timestamp)]
                    proposals,humans,boats = self.actions.predict(frame,[*priority,*rotated],crop_limit=4)
                    self.crop_cursor += 4
                else:
                    proposals,humans,boats = self.actions.predict(frame,[*primary,*self.visibility.rois(timestamp)])
                proposals,rejected_actions = filter_actions(proposals,primary,humans,boats,frame.shape[1],frame.shape[0])
                proposals = [{**p,'inference_timestamp_s':timestamp} for p in proposals]
            except Exception as exc:
                self.models['drowning'] = {'state':'failed','message':str(exc)}
                self.actions.close(); self.actions = None
        action_ms = (time.perf_counter()-action_start)*1000
        people = [p for p in proposals if p['score'] >= .5 and p.get('crop_track_id') not in {o['track_id'] for o in primary if o['class']=='swimmer'}]
        if self.scene_type == 'swimmers_only':
            people += [h for h in humans if h['score'] >= .4 and not any(box_iou(h['bbox_xyxy_px'],p['bbox_xyxy_px']) >= .2 for p in people)]
        elif not cut:
            people += [h for h in recover_known_swimmers(humans,primary,self.identity.tracks,timestamp)
                       if not any(box_iou(h['bbox_xyxy_px'],p['bbox_xyxy_px']) >= .2 for p in people)]
        extras = self.people.update(people,self.index,timestamp)
        for o in extras: o['track_id'] = 2*o['track_id']+1
        objects,_ = reconcile(primary,proposals,humans,boats,extras,self.scene_type!='swimmers_only',
                              ['swimmer'] if self.scene_type=='swimmers_only' else None)
        objects = self.identity.update(objects,frame,self.index,timestamp,cut)
        matched = associate([o for o in objects if o['class']=='swimmer'],proposals)
        for obj in objects:
            action = matched.get(obj['track_id'])
            if action:
                obj['distress_action'] = {'label':action['label'],'score':action['score'],'requires_review':action['class']=='drown'}
        record = {'schema_version':1,'coordinate_space':'pixel','frame':self.index,'timestamp_s':timestamp,
                  'scene_cut':bool(cut),'objects':objects,
                  'unobserved_swimmers':self.visibility.update(objects,timestamp,cut)}
        observations = self.distress.update(record,proposals,action_ready=self.actions is not None)
        for observation in observations:
            action=observation.get('action')
            if not action or action['class']!='drown' or action['score']<.55:
                continue
            key=(observation['track_id'],action['label'])
            previous=self.review_candidates.get(key)
            self.review_candidates[key]={'track_id':key[0],'label':key[1],'last_seen_s':timestamp,
                'first_seen_s':previous['first_seen_s'] if previous else timestamp,
                'action_score':action['score'],'peak_score':max(previous['peak_score'] if previous else 0,action['score']),
                'distinct_predictions':previous['distinct_predictions']+1 if previous else 1,
                'state':'unconfirmed','requires_review':True}
        self.review_candidates=dict(sorted(self.review_candidates.items(),key=lambda item:item[1]['last_seen_s'])[-50:])
        warn_on_lost_distress(self.distress,record)
        rip_regions = []
        rip_start = time.perf_counter()
        if self.rip is not None:
            try:
                rip_regions = self.rip_evidence.update(self.rip.predict(frame),self.index,timestamp)
            except Exception as exc:
                self.models['rip_current'] = {'state':'failed','message':str(exc)}
                self.rip = None
        rip_ms = (time.perf_counter()-rip_start)*1000
        annotated = render_analysis_frame(frame.copy(),record)
        for region in rip_regions:
            x1,y1,x2,y2 = map(round,region['bbox_xyxy_px'])
            cv2.rectangle(annotated,(x1,y1),(x2,y2),(209,224,24),2)
            cv2.putText(annotated,f"Rip candidate #{region['region_id']} | {region['score']:.2f}",
                        (x1,max(20,y1-8)),cv2.FONT_HERSHEY_SIMPLEX,.55,(209,224,24),2)
        ok,jpeg = cv2.imencode('.jpg',annotated,[cv2.IMWRITE_JPEG_QUALITY,82])
        if not ok: raise RuntimeError('Could not encode analyzed frame')
        self.distress.events = self.distress.events[-50:]
        self.rip_evidence.events = self.rip_evidence.events[-50:]
        rip_candidates = [{'region_id':key,'last_seen_s':t['last_s'],
            'bbox_xyxy_px':t['box'],'model_score':float(np.mean([s for _,s in t['samples']])),
            'peak_score':max(s for _,s in t['samples']),'distinct_predictions':len(t['samples']),
            'evidence_span_s':t['samples'][-1][0]-t['samples'][0][0],
            'crop_only':not any(s=='full_frame' for s in t['sources'].values()),'state':'unconfirmed'}
            for key,t in self.rip_evidence.tracks.items() if not t['warned']]
        self.identity.recoveries = self.identity.recoveries[-100:]
        active_ids = set(self.identity.tracks)
        self.identity.aliases = {k:v for k,v in self.identity.aliases.items() if v in active_ids}
        self.distress.last_alert = {k:v for k,v in self.distress.last_alert.items() if timestamp-v <= 60}
        for history in (self.tracks.history,self.people.history,self.identity.history): prune_history(history,timestamp)
        # Short trails reduce wire size while preserving internal identity history.
        for obj in objects: obj['trail'] = obj['trail'][-12:]
        self.index += 1
        return {'sequence':sequence,'captured_at_s':timestamp,'tracking':record,'models':dict(self.models),
                'width_px':frame.shape[1],'height_px':frame.shape[0],
                'distress_events':list(self.distress.events),'rip_regions':rip_regions,
                'rip_candidates':rip_candidates,'rip_diagnostics':getattr(self.rip,'last_diagnostics',{}),
                'distress_candidates':[c for c in self.review_candidates.values() if not any(e['track_id']==c['track_id'] for e in self.distress.events)],
                'distress_observations':observations,
                'action_diagnostics':{'proposals':proposals,'rejected':rejected_actions},
                'rip_events':list(self.rip_evidence.events),'processing_ms':round((time.perf_counter()-started)*1000,1),
                'performance':{'identification_ms':round(detector_ms,1),'drowning_ms':round(action_ms,1),
                               'rip_ms':round(rip_ms,1),'sample_gap_s':sample_gap,
                               'coverage_limited':sample_gap is not None and sample_gap > .75},
                'alert_policy':{'window_seconds':6,'max_gap_seconds':2.5,'distinct_predictions':{'active':3,'passive':4,'crop_only':5,'rip':3},
                                'rip':{'minimum_span_s':1,'crop_only_minimum_peak':.75},
                                'contact_loss':{'active_full_frame_predictions':2,'minimum_loss_seconds':.75,'minimum_peak':.8}},
                'image_base64':base64.b64encode(jpeg).decode('ascii')}

    def close(self):
        if self.actions is not None: self.actions.close()
        temporary = getattr(self.detector,'_temporary_weights',None)
        if temporary: temporary.cleanup()


def camera_worker(pipe,scene_type):
    """Keep CPU thread tuning and ML runtime state out of upload analysis."""
    engine = None
    try:
        activate_live_runtime()
        import torch
        torch.set_num_threads(4)
        engine = LiveEngine(scene_type)
        warm = np.zeros((720,1280,3),np.uint8)
        engine.detector.detect(warm)
        if engine.actions: engine.actions.predict(warm,[],crop_limit=0)
        if engine.rip: engine.rip.predict(warm)
        torch.set_num_threads(4)
        pipe.send({'models':engine.models})
        while True:
            task = pipe.recv()
            if task is None: break
            frame,timestamp,sequence = task
            try:
                torch.set_num_threads(4)
                pipe.send({'result':engine.process(frame,timestamp,sequence)})
            except Exception as exc: pipe.send({'error':str(exc)})
    except (EOFError,BrokenPipeError):
        pass
    except Exception as exc:
        try: pipe.send({'error':str(exc)})
        except (EOFError,BrokenPipeError): pass
    finally:
        if engine: engine.close()
        pipe.close()


class LiveWorker:
    def __init__(self,scene_type):
        context = multiprocessing.get_context('spawn')
        self.pipe,child_pipe = context.Pipe()
        self.process_handle = context.Process(target=camera_worker,args=(child_pipe,scene_type),daemon=True)
        self.process_handle.start()
        child_pipe.close()
        try:
            ready = self.receive(75)
            self.models = ready['models']
        except Exception:
            self.close()
            raise

    def receive(self,timeout):
        if not self.pipe.poll(timeout): raise RuntimeError('Live model worker timed out')
        response = self.pipe.recv()
        if 'error' in response: raise RuntimeError(response['error'])
        return response

    def process(self,frame,timestamp,sequence):
        try:
            self.pipe.send((frame,timestamp,sequence))
            result = self.receive(25)['result']
            if result['sequence'] != sequence: raise RuntimeError('Live worker returned a stale frame')
            return result
        except Exception:
            self.close()
            raise

    def close(self):
        try: self.pipe.send(None)
        except (BrokenPipeError,EOFError,OSError): pass
        self.process_handle.join(timeout=2)
        if self.process_handle.is_alive():
            self.process_handle.terminate();self.process_handle.join(timeout=2)
        self.pipe.close()


class StartLive(BaseModel):
    scene_type: str = 'auto'


class Session:
    def __init__(self, engine, client_kind='camera'):
        self.engine = engine
        self.client_kind = client_kind
        self.created = self.touched = time.monotonic()
        self.lock = Lock()
        self.sequence = -1
        self.captured = -1.
        self.diagnostics = deque(maxlen=120)
        self.diagnostic_jpeg = None


class LiveSessions:
    def __init__(self, factory=LiveWorker, limit=2):
        self.factory, self.limit = factory, limit
        self.sessions = {}
        self.lock = Lock()
        self.loading = 0

    def reap(self):
        with self.lock:
            for key,session in list(self.sessions.items()):
                if (time.monotonic()-session.touched > IDLE_SECONDS or time.monotonic()-session.created > MAX_SESSION_SECONDS) and session.lock.acquire(False):
                    try:
                        session.engine.close();del self.sessions[key]
                    finally: session.lock.release()

    def start(self, scene_type, client_kind='camera'):
        self.reap()
        with self.lock:
            if len(self.sessions)+self.loading >= self.limit:
                raise HTTPException(429,'Live camera capacity reached. Stop another live session or wait two minutes.')
            self.loading += 1
        try:
            engine = self.factory(scene_type)
            key = str(uuid4())
            with self.lock: self.sessions[key] = Session(engine,client_kind)
            return {'session_id':key,'models':engine.models,'idle_timeout_s':IDLE_SECONDS,
                    'max_session_s':MAX_SESSION_SECONDS,'max_frame_bytes':MAX_BYTES}
        finally:
            with self.lock: self.loading -= 1

    def process(self, key, data, sequence, captured):
        self.reap()
        with self.lock:
            session = self.sessions.get(key)
            if session is None: raise HTTPException(410,'Live session ended. Start the camera again.')
            if not session.lock.acquire(False): raise HTTPException(409,'A camera frame is already being analyzed')
        try:
            if sequence <= session.sequence or captured <= session.captured:
                raise HTTPException(409,'Stale frame rejected; capture a new frame')
            try: frame = decode_camera_frame(data)
            except Exception as exc: raise HTTPException(400,str(exc)) from exc
            session.touched = time.monotonic()
            result = session.engine.process(frame,captured,sequence)
            session.sequence,session.captured = sequence,captured
            session.diagnostic_jpeg = data
            session.diagnostics.append(copy.deepcopy({
                'sequence':sequence,'captured_at_s':captured,'client_kind':session.client_kind,'processing_ms':result.get('processing_ms'),
                'performance':result.get('performance'),'scene_cut':result['tracking'].get('scene_cut'),
                'action_diagnostics':result.get('action_diagnostics'),
                'models':result.get('models'),'rip_regions':result.get('rip_regions',[]),
                'rip_candidates':result.get('rip_candidates',[]),'rip_diagnostics':result.get('rip_diagnostics'),
                'swimmers':[{k:o[k] for k in ('track_id','confidence','bbox_xyxy_px','distress_action') if k in o}
                            for o in result['tracking']['objects'] if o['class']=='swimmer'],
                'unobserved_swimmers':result['tracking'].get('unobserved_swimmers',[]),
                'distress_events':result.get('distress_events',[]),'rip_events':result.get('rip_events',[])}))
            session.touched = time.monotonic()
            return result
        finally: session.lock.release()

    def stop(self,key):
        with self.lock: session = self.sessions.get(key)
        if session is None: return
        with session.lock:
            with self.lock:
                if self.sessions.pop(key,None) is not None: session.engine.close()

    def diagnostics(self,key):
        with self.lock:
            session = self.sessions.get(key)
            if session is None: raise HTTPException(410,'Live session ended')
        with session.lock:
            return copy.deepcopy(list(session.diagnostics))

    def diagnostic_frame(self,key):
        with self.lock:
            session = self.sessions.get(key)
            if session is None: raise HTTPException(410,'Live session ended')
        with session.lock:
            if session.diagnostic_jpeg is None: raise HTTPException(404,'No analyzed camera frame yet')
            return Response(session.diagnostic_jpeg,media_type='image/jpeg',headers={
                'Cache-Control':'no-store','X-Frame-Sequence':str(session.sequence),'X-Captured-At':str(session.captured)})

    def close(self):
        for key in list(self.sessions): self.stop(key)


sessions = LiveSessions()


@router.post('/sessions',status_code=201)
async def start_live(options: StartLive, request: Request):
    if options.scene_type not in {'auto','swimmers_only'}: raise HTTPException(400,'Unknown scene type')
    kind = 'replay' if request.headers.get('user-agent','').lower().startswith('python-urllib') else 'camera'
    try: return await run_in_threadpool(sessions.start,options.scene_type,kind)
    except HTTPException: raise
    except Exception as exc: raise HTTPException(503,f'Live model could not start: {exc}') from exc


@router.post('/sessions/{key}/frame')
async def live_frame(key: str, request: Request):
    if request.headers.get('content-type','').split(';')[0] != 'image/jpeg':
        raise HTTPException(415,'Send image/jpeg camera frames')
    try:
        sequence = int(request.headers['x-frame-sequence'])
        captured = float(request.headers['x-captured-at'])
        if sequence < 0 or not math.isfinite(captured) or not 0 <= captured <= MAX_SESSION_SECONDS+60: raise ValueError()
    except (KeyError,ValueError): raise HTTPException(400,'Valid frame sequence and elapsed capture time required')
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>MAX_BYTES: raise HTTPException(413,'Camera frame exceeds 2 MB')
    try: return await run_in_threadpool(sessions.process,key,bytes(data),sequence,captured)
    except HTTPException: raise
    except Exception as exc: raise HTTPException(500,f'Live frame analysis failed: {exc}') from exc


@router.delete('/sessions/{key}',status_code=204)
async def stop_live(key: str):
    await run_in_threadpool(sessions.stop,key)


@router.get('/sessions/{key}/diagnostics')
async def live_diagnostics(key: str):
    # Bounded metadata in memory only: no raw or annotated camera images.
    return await run_in_threadpool(sessions.diagnostics,key)


@router.get('/sessions/{key}/diagnostic-frame')
async def live_diagnostic_frame(key: str, request: Request):
    # Explicit local developer export of the one current in-memory frame.
    # Unavailable to LAN callers; no image history is stored by the service.
    if request.client is None or request.client.host not in {'127.0.0.1','::1'}:
        raise HTTPException(403,'Camera diagnostic export is local only')
    return await run_in_threadpool(sessions.diagnostic_frame,key)
