"""Read-only distress sidecar: never changes detections, identities or tracks.

Movement rules are image-space proxies, enabled only for an explicitly verified
stationary/stabilized camera and water context. Model proposals remain warnings
for review, not verified drowning diagnoses.
"""
import argparse
from collections import deque
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from .config import ROOT

UPSTREAM_REVISION = "b75850a26cc8e6b255bd09ffb26c333adce4fa2a"
INDICATORS = {
    "repeated_submersion": "visual contact loss is tracked separately; gaps cannot confirm underwater submersion",
    "little_horizontal_movement": "conditional proxy: verified motion reference and water context required",
    "frantic_arm_motion": "unavailable: no arm keypoints or dedicated validated action label",
    "head_barely_above_water": "unavailable: no head/waterline estimator",
    "offshore_drift": "conditional proxy: verified motion reference, water context and offshore direction required",
    "sudden_speed_reduction": "conditional proxy: verified motion reference and water context required",
    "swimmer_separation": "conditional proxy: nearby tracked swimmers and verified motion reference required",
    "unusual_body_orientation": "unavailable: no pose/orientation estimator",
}


def settings_from_file(path=None):
    path = Path(path or os.environ.get("AEGIS_DROWNING_CONFIG", ROOT / "config/drowning.local.json"))
    cfg = {"repository": str(ROOT / "third_party/drowning-detection"), "checkpoint": None, "backend": "yolo",
           "architecture": "2Dseq_tiny", "device": "cpu", "score_threshold": .75,
           "motion_reference": "uncalibrated", "water_confirmed": False, "offshore_direction": None}
    if path.is_file():
        supplied = json.loads(path.read_text(encoding="utf-8"))
        cfg.update(supplied)
        if supplied.get('checkpoint') and 'backend' not in supplied:
            cfg['backend'] = 'z5cc'
    if cfg['backend'] not in {'yolo','z5cc'}:
        raise ValueError('backend must be yolo or z5cc')
    for key in ("repository", "checkpoint"):
        if cfg[key]:
            value = Path(cfg[key])
            cfg[key] = str(value if value.is_absolute() else ROOT / value)
    if cfg["architecture"] not in {"2Dseq_tiny", "2Dseq_medium", "YOWOv2_tiny", "YOWOv2_medium"}:
        raise ValueError("Use an upstream 2Dseq or YOWOv2 config matching the checkpoint")
    if cfg["motion_reference"] not in {"uncalibrated", "stationary", "stabilized"}:
        raise ValueError("Invalid motion_reference")
    if not isinstance(cfg["water_confirmed"], bool):
        raise ValueError("water_confirmed must be a boolean")
    if not .5 <= cfg["score_threshold"] <= 1:
        raise ValueError("score_threshold must be between .5 and 1")
    direction = cfg["offshore_direction"]
    if direction is not None:
        if len(direction) != 2 or not all(math.isfinite(x) for x in direction) or math.hypot(*direction) == 0:
            raise ValueError("offshore_direction must be a finite nonzero image vector")
        cfg["offshore_direction"] = [x / math.hypot(*direction) for x in direction]
    return cfg


def box_iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = lambda v: max(0, v[2] - v[0]) * max(0, v[3] - v[1])
    return intersection / max(1e-9, area(a) + area(b) - intersection)


def associate(swimmers, proposals):
    """Reject ambiguous overlapping boxes instead of assigning a warning to the wrong person."""
    matches = {}
    for p in sorted(proposals, key=lambda p: p["score"], reverse=True):
        ranked = sorted([(box_iou(o["bbox_xyxy_px"], p["bbox_xyxy_px"]), o["track_id"]) for o in swimmers], reverse=True)
        if not ranked or ranked[0][0] < .3 or (len(ranked) > 1 and ranked[0][0] - ranked[1][0] < .25):
            continue
        matches.setdefault(ranked[0][1], p)
    return matches


@dataclass
class Sample:
    time: float
    x: float
    y: float
    size: float
    neighbor: int | None
    neighbor_distance: float | None


class DistressEngine:
    def __init__(self, cfg):
        self.cfg = cfg
        self.history = {}
        self.pending = {}
        self.last_alert = {}
        self.events = []
        self.action_windows = {}

    def action_warning(self, tid, proposal, record):
        """Count independent inferences, never repeated playback frames as votes."""
        now = record['timestamp_s']
        window = self.action_windows.setdefault(tid, deque())
        while window and now-window[0][0] > self.cfg.get('action_window_seconds',2):
            window.popleft()
        if proposal and proposal['class'] == 'swim' and proposal['score'] >= .7:
            window.clear()
        if proposal and proposal['class'] == 'drown' and proposal['score'] >= .55:
            token = proposal.get('inference_timestamp_s')
            if token is None:
                token = (proposal.get('label'), proposal['score'], tuple(proposal['bbox_xyxy_px']))
            if not window or token != window[-1][1]:
                window.append((now, token, proposal))
        active = [v for v in window if v[2].get('label') == 'Active drowning']
        passive = [v for v in window if v[2].get('label') == 'Possible Passive Drowner']
        support = active if len(active) >= 3 else passive
        required = 3 if support is active else 4
        minimum_span = .2 if support is active else .4
        minimum_peak = .8 if support is active else .9
        # Enlarged crops of tiny aerial people can be confidently mislabeled.
        # A crop-only warning needs stronger and longer support than full-frame evidence.
        crop_only = bool(support) and all('crop_track_id' in v[2] for v in support)
        if crop_only:
            required, minimum_span = 5, .6
            minimum_peak = .9 if support is active else .95
        if (len(support) < required or support[-1][0]-support[0][0] < minimum_span-1e-6
                or max(v[2]['score'] for v in support) < minimum_peak
                or now-self.last_alert.get(tid,-math.inf) < 10):
            return
        score = sum(v[2]['score'] for v in support)/len(support)
        self.events.append({'track_id':tid,'frame':record['frame'],'timestamp_s':now,
                           'start_s':support[0][0],'type':'possible_distress','requires_review':True,
                           'signals':['active_drowning' if support is active else 'possible_passive_drowning'],
                           'metrics':{'distinct_predictions':len(support),'peak_action_score':max(v[2]['score'] for v in support),
                                      'evidence_span_seconds':support[-1][0]-support[0][0]},
                           'action_score':score,'score_basis':'mean of distinct supporting model predictions'})
        self.last_alert[tid] = now

    def update(self, record, proposals=(), context_s=0, action_ready=None):
        now = record["timestamp_s"]
        if record.get('scene_cut'):
            self.pending.clear()
            self.history.clear()
            self.action_windows.clear()
            self.last_alert.clear()
        swimmers = [o for o in record["objects"] if o["class"] == "swimmer" and o["confidence"] >= self.cfg.get('minimum_swimmer_confidence',.3)]
        neural = associate(swimmers, proposals)
        observations = []
        for o in swimmers:
            tid = o["track_id"]
            x, y = o["center_px"]
            box = o["bbox_xyxy_px"]
            size = max(4., math.sqrt(max(1., (box[2]-box[0]) * (box[3]-box[1]))))
            neighbors = [(math.hypot(x-p["center_px"][0], y-p["center_px"][1])/size, p["track_id"])
                         for p in swimmers if p["track_id"] != tid]
            nearest = min(neighbors) if neighbors else (None, None)
            h = self.history.setdefault(tid, deque())
            if h and (now - h[-1].time > .5 or math.hypot(x-h[-1].x, y-h[-1].y) > 3 * size):
                h.clear()  # Track gap, edit or likely ID jump: discard temporal evidence.
            h.append(Sample(now, x, y, size, nearest[1], nearest[0]))
            while h and now - h[0].time > 8:
                h.popleft()
            signals = []
            metrics = {"history_seconds": round(now-h[0].time, 3), "nearest_swimmer_body_lengths": nearest[0]}
            if now-h[0].time >= 4:
                old = h[0]
                scale = sum(s.size for s in h)/len(h)
                mid = min(h, key=lambda s: abs(s.time-(now-2)))
                before = math.hypot(mid.x-old.x, mid.y-old.y)/max(.01, mid.time-old.time)/scale
                recent = math.hypot(x-mid.x, y-mid.y)/max(.01, now-mid.time)/scale
                excursion = max(math.hypot(s.x-old.x, s.y-old.y) for s in h)/scale
                metrics.update(recent_speed_body_lengths_s=recent, previous_speed_body_lengths_s=before,
                               excursion_body_lengths=excursion)
                if excursion < .6:
                    signals.append("little_horizontal_movement")
                if before >= .4 and recent <= .25 * before:
                    signals.append("sudden_speed_reduction")
                if (excursion >= 1 and nearest[0] is not None and old.neighbor == nearest[1] and old.neighbor_distance is not None
                        and old.neighbor_distance < 4 and nearest[0] > 6 and nearest[0] > 2*old.neighbor_distance):
                    signals.append("swimmer_separation")
                direction = self.cfg.get("offshore_direction")
                if direction and (x-old.x)*direction[0]+(y-old.y)*direction[1] > 2*scale:
                    signals.append("offshore_drift")
            reference = self.cfg["motion_reference"] in {"stationary", "stabilized"}
            motion_enabled = reference and self.cfg["water_confirmed"]
            evidence = signals if motion_enabled else []
            p = neural.get(tid)
            if action_ready and self.cfg.get('backend') == 'yolo':
                self.action_warning(tid,p,record)
            threshold = .55 if action_ready and self.cfg.get('backend') == 'yolo' else self.cfg['score_threshold']
            if (p and p["class"] == "drown" and p["score"] >= threshold
                    and (action_ready if action_ready is not None else context_s >= 4)):
                signal = {'Active drowning':'active_drowning', 'Possible Passive Drowner':'possible_passive_drowning'}.get(p.get('label'),'upstream_drown_action')
                evidence = [*evidence, signal]
            # Persisted neural result OR multiple independent movement proxies.
            neural_candidate = bool({'upstream_drown_action','active_drowning','possible_passive_drowning'} & set(evidence))
            candidate = (neural_candidate and not (action_ready and self.cfg.get('backend') == 'yolo')) or len([s for s in evidence if s in signals]) >= 2
            pending = self.pending.get(tid)
            signature = tuple(sorted(evidence))
            if candidate:
                if pending is None or pending[1] != signature or now-pending[2] > .5:
                    pending = (now, signature, now)
                else:
                    pending = (pending[0], signature, now)
                self.pending[tid] = pending
                if now-pending[0] >= 2 and now-self.last_alert.get(tid, -math.inf) >= 10:
                    self.events.append({"track_id": tid, "frame": record["frame"], "timestamp_s": now,
                                        "start_s": pending[0], "type": "possible_distress", "requires_review": True,
                                        "signals": evidence, "metrics": metrics,
                                        "action_score": p["score"] if p else None})
                    self.last_alert[tid] = now
            else:
                self.pending.pop(tid, None)
            observations.append({"track_id": tid, "signals": evidence, "image_space_proxies": signals,
                                 "motion_alerts_enabled": motion_enabled, "metrics": metrics,
                                 "action": p, "state": "review_candidate" if candidate or neural_candidate else "undetermined"})
        # Bound memory and invalidate a warning if the swimmer disappears.
        present = {o["track_id"] for o in swimmers}
        for lost in record.get('unobserved_swimmers',[]):
            for event in reversed(self.events):
                if event['track_id'] == lost['track_id'] and 0 <= now-event['timestamp_s'] <= 1.5:
                    if 'visual_contact_lost' not in event['signals']:
                        event['signals'].append('visual_contact_lost')
                    event['metrics']['last_seen_s'] = lost['last_seen_s']
                    break
        self.pending = {tid: p for tid, p in self.pending.items() if tid in present}
        self.history = {tid: h for tid, h in self.history.items() if now-h[-1].time < 10}
        self.action_windows = {tid:w for tid,w in self.action_windows.items() if w and now-w[-1][0] <= self.cfg.get('action_memory_seconds',1.5)}
        return observations


def analyze_distress(source, tracks, output, settings_path=None, actions_path=None, classifier_metadata=None):
    tracks, output = Path(tracks), Path(output)
    cfg = settings_from_file(settings_path)
    classifier = {"state": "missing_checkpoint", "architecture": cfg["architecture"],
                  "source": "https://github.com/Z5cc/drowning-detection", "revision": UPSTREAM_REVISION,
                  "message": "No trained swim/drown checkpoint configured. No neural drowning predictions were made."}
    proposal_path = Path(actions_path) if actions_path else output.with_suffix(".actions.jsonl")
    if cfg['backend'] == 'yolo':
        try:
            if actions_path and classifier_metadata:
                classifier = classifier_metadata
            else:
                from .action_yolo import run_video
                classifier = run_video(source,tracks,proposal_path,device=cfg['device'])
        except Exception as exc:
            classifier = {'state':'failed','backend':'yolo','message':str(exc)}
    elif cfg["checkpoint"]:
        classifier["state"] = "failed"
        try:
            if not Path(cfg["checkpoint"]).is_file():
                raise FileNotFoundError("Configured drowning checkpoint does not exist")
            if not Path(cfg["repository"], "models/yowo/build.py").is_file():
                raise FileNotFoundError("Run scripts/setup_drowning.ps1 to fetch the upstream source")
            settings = output.with_suffix(".settings.json")
            settings.write_text(json.dumps(cfg), encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "vision/drowning_worker.py"), str(settings),
                                     str(source), str(proposal_path)], capture_output=True, text=True, timeout=3600)
            if result.returncode:
                raise RuntimeError(result.stderr[-2000:])
            classifier.update(state="ready", message="Upstream action predictions available; domain validation is still required.",
                              checkpoint_sha256=hashlib.sha256(Path(cfg["checkpoint"]).read_bytes()).hexdigest())
        except Exception as exc:
            classifier["message"] = str(exc)
        finally:
            output.with_suffix(".settings.json").unlink(missing_ok=True)
    actions = iter(())
    action_file = None
    if classifier["state"] == "ready":
        action_file = proposal_path.open(encoding="utf-8")
        actions = (json.loads(line) for line in action_file)
    next_action = next(actions, None)
    current = None
    engine = DistressEngine(cfg)
    samples = []
    next_sample = 0
    with tracks.open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            while next_action and next_action["timestamp_s"] <= record["timestamp_s"]:
                current = next_action
                next_action = next(actions, None)
            fresh = current and record["timestamp_s"]-current["timestamp_s"] <= .25
            if fresh and current.get('scene_cut') and current['frame'] == record['frame']:
                record = {**record,'scene_cut':True}
            proposals = current['proposals'] if fresh else ()
            if fresh and 'inference_timestamp_s' in current:
                proposals = [{**p,'inference_timestamp_s':current['inference_timestamp_s']} for p in proposals]
            observations = engine.update(record, proposals,
                                         current.get("context_s", 0) if fresh else 0,
                                         action_ready=bool(fresh and current.get('context_ready',False)))
            if record["timestamp_s"] >= next_sample:
                samples.append({"frame": record["frame"], "timestamp_s": record["timestamp_s"], "swimmers": observations})
                next_sample = record["timestamp_s"] + 1
    if action_file:
        action_file.close()
    report = {"schema_version": 1, "status": "complete", "classifier": classifier,
              "indicator_capabilities": INDICATORS, "motion_reference": cfg["motion_reference"],
              "water_confirmed": cfg["water_confirmed"], "offshore_direction": cfg["offshore_direction"],
              "alert_policy": {"distinct_predictions_required": {"active":3,"passive":4},
                               "minimum_score":.55,"minimum_peak_score":{"active":.8,"passive":.9},"window_seconds":2,
                               "crop_only":{"distinct_predictions":5,"minimum_span_seconds":.6,
                                            "minimum_peak_score":{"active":.9,"passive":.95}},
                               "score_is_probability":False},
              "limitations": ["Warnings require human review; absence of warnings does not establish safety.",
                              "Image-space movement is not physical swimming speed.",
                              "Upstream lifeguard footage is not validation on aerial drone footage."],
              "events": engine.events, "samples": samples}
    output.write_text(json.dumps(report, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("tracks", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--settings", type=Path)
    args = parser.parse_args()
    report = analyze_distress(args.source, args.tracks, args.output, args.settings)
    print(json.dumps({"classifier": report["classifier"], "review_events": len(report["events"])}))
