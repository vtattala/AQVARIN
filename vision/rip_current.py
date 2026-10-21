"""Independent RipScout sediment-rip inference; never changes swimmer outputs.

See assets/models/ripscout for upstream revision, hashes and license. The upstream
Swift implementation resizes the entire image despite its center-crop comment.
"""
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from .config import ROOT
from .distress import box_iou

ASSETS = ROOT / 'assets/models/ripscout'


class RipScoutModel:
    def __init__(self):
        from ai_edge_litert.interpreter import Interpreter
        self.manifest = json.loads((ASSETS/'provenance.json').read_text())
        for name, digest in self.manifest['files'].items():
            if hashlib.sha256((ASSETS/name).read_bytes()).hexdigest() != digest:
                raise ValueError(f'RipScout checkpoint verification failed: {name}')
        self.labels = (ASSETS/'labelmap1.txt').read_text().splitlines()
        if self.labels != ['???','sediment_rip']:
            raise ValueError('Unexpected RipScout label mapping')
        self.interpreter = Interpreter(model_path=str(ASSETS/'detect1.tflite'), num_threads=2)
        self.interpreter.allocate_tensors()
        self.input = self.interpreter.get_input_details()[0]
        self.outputs = self.interpreter.get_output_details()
        if list(self.input['shape']) != [1, 300, 300, 3] or len(self.outputs) != 4:
            raise ValueError('Unexpected RipScout tensor signature')

    def predict(self, frame):
        height, width = frame.shape[:2]
        rgb = cv2.cvtColor(cv2.resize(frame, (300, 300)), cv2.COLOR_BGR2RGB)
        if self.input['dtype'] == np.uint8:
            tensor = rgb
        elif self.input['dtype'] == np.float32:
            tensor = (rgb.astype(np.float32)-127.5)/127.5
        else:
            raise ValueError('Unsupported RipScout input dtype')
        self.interpreter.set_tensor(self.input['index'], tensor[None])
        self.interpreter.invoke()
        boxes, classes, scores, count = [self.interpreter.get_tensor(d['index']) for d in self.outputs]
        return decode_predictions(boxes[0], classes[0], scores[0], int(count[0]), width, height)


def decode_predictions(boxes, classes, scores, count, width, height):
    regions = []
    for box, class_id, score in zip(boxes[:count], classes[:count], scores[:count]):
        if not np.isfinite(score) or score < .5 or score > 1 or class_id != 0 or not np.isfinite(box).all():
            continue
        y1, x1, y2, x2 = np.clip(box, 0, 1)
        if x2 <= x1 or y2 <= y1:
            continue
        regions.append({'label':'sediment_rip', 'score':float(score),
                        'bbox_xyxy_px':[float(x1*width), float(y1*height), float(x2*width), float(y2*height)]})
    return regions


class RipEvidence:
    """Require three spatially consistent independent samples spanning >=1 sec.

    Persistence is a review criterion, not hydrodynamic confirmation. Matching
    is one-to-one per sample. No swimmer IDs or drowning scores are used.
    """
    def __init__(self, window_seconds=2, max_gap_seconds=1.1):
        self.tracks = {}
        self.next_id = 1
        self.events = []
        self.window_seconds = window_seconds
        self.max_gap_seconds = max_gap_seconds

    def update(self, regions, frame, timestamp):
        self.tracks = {k:v for k,v in self.tracks.items() if timestamp-v['last_s'] <= self.max_gap_seconds}
        used = set()
        for region in regions:
            matches = sorted([(box_iou(region['bbox_xyxy_px'], t['box']), k)
                              for k,t in self.tracks.items() if k not in used], reverse=True)
            key = matches[0][1] if matches and matches[0][0] >= .3 else self.next_id
            if key == self.next_id:
                self.next_id += 1
                self.tracks[key] = {'box':region['bbox_xyxy_px'], 'start_s':timestamp,
                                    'last_s':timestamp, 'samples':[], 'sources':{}, 'warned':False}
            track = self.tracks[key]
            used.add(key)
            track['box'] = region['bbox_xyxy_px']
            if not track['samples'] or timestamp > track['last_s']:
                track['samples'].append((timestamp, region['score']))
                track['sources'][timestamp] = region.get('evidence_source','full_frame')
            track['last_s'] = timestamp
            track['samples'] = [(t,s) for t,s in track['samples'] if timestamp-t <= self.window_seconds]
            track['sources'] = {t:s for t,s in track['sources'].items() if timestamp-t <= self.window_seconds}
            region['region_id'] = key
            if not track['warned'] and self.warning_ready(track,timestamp):
                track['warned'] = True
                self.events.append({'region_id':key, 'frame':frame, 'timestamp_s':timestamp,
                    'start_s':track['samples'][0][0], 'type':'possible_rip_current', 'requires_review':True,
                    'bbox_xyxy_px':region['bbox_xyxy_px'],
                    'model_score':float(np.mean([s for _,s in track['samples']])),
                    'peak_score':max(s for _,s in track['samples']), 'distinct_predictions':len(track['samples'])})
        return regions

    def warning_ready(self, track, timestamp):
        return len(track['samples']) >= 3 and timestamp-track['samples'][0][0] >= 1


def analyze_rip_current(source: Path, output: Path, model=None):
    report = {'schema_version':1, 'status':'complete', 'model':{'state':'ready', 'backend':'ripscout',
        'label':'sediment_rip', 'revision':'9c42c5db12ae914137a022242a19612710a85b11'},
        'coordinate_space':'pixel', 'sample_interval_seconds':.5, 'threshold':.5,
        'scope':'Visible sediment-plume rip candidates; not all rip-current types. Scores are not calibrated probabilities.',
        'samples':[], 'events':[]}
    cap = None
    try:
        model = model or RipScoutModel()
        cap = cv2.VideoCapture(str(source))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not cap.isOpened() or not np.isfinite(fps) or fps <= 0:
            raise ValueError('Video cannot be decoded for rip-current analysis')
        report['width_px'] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        report['height_px'] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        evidence = RipEvidence()
        frame_number, next_time = 0, 0.
        previous_hist = None
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            timestamp = frame_number/fps
            if timestamp+1e-6 >= next_time:
                # Reset temporal evidence at hard scene cuts, never join separate shots.
                gray = cv2.cvtColor(cv2.resize(frame,(64,64)),cv2.COLOR_BGR2GRAY)
                hist = cv2.calcHist([gray],[0],None,[32],[0,256])
                cv2.normalize(hist,hist)
                if previous_hist is not None and cv2.compareHist(previous_hist,hist,cv2.HISTCMP_BHATTACHARYYA) > .65:
                    evidence.tracks.clear()
                previous_hist = hist
                regions = evidence.update(model.predict(frame), frame_number, timestamp)
                report['samples'].append({'frame':frame_number,'timestamp_s':timestamp,'regions':regions})
                next_time = timestamp+.5
            frame_number += 1
        if frame_number == 0:
            raise ValueError('Video has no readable frames')
        report['events'] = evidence.events
        report['sampled_frames'] = len(report['samples'])
        report['observations'] = sum(len(s['regions']) for s in report['samples'])
    except Exception as exc:
        report.update(status='failed', error=str(exc), samples=[], events=[])
        report['model']['state'] = 'failed'
    finally:
        if cap is not None:
            cap.release()
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
