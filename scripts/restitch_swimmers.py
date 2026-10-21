"""Rebuild stable swimmer IDs from saved detections without rerunning either model."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import cv2

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from vision.swimmer_identity import SwimmerIdentity
from vision.action_yolo import VisibilityWatch,render_analysis_frame
from vision.distress import analyze_distress
from vision.playback import prepare_playback
from vision.api import _status_path,_save_status

def restitch(job_id):
    directory=_status_path(job_id).parent
    raw=directory/'analysis.before_identity.jsonl'
    if not raw.exists():raw.write_bytes((directory/'analysis.jsonl').read_bytes())
    primary_digest=hashlib.sha256((directory/'tracks.jsonl').read_bytes()).hexdigest()
    records=[json.loads(l) for l in raw.read_text().splitlines()]
    reserved={o['track_id'] for r in records for o in r['objects'] if o['class']!='swimmer'}
    identity=SwimmerIdentity(reserved,max(o['track_id'] for r in records for o in r['objects'])+1)
    visibility=VisibilityWatch()
    source=next(directory.glob('source.*'))
    cap=cv2.VideoCapture(str(source))
    size=(int(cap.get(3)),int(cap.get(4)))
    video_path=directory/'analysis.identity.mp4'
    writer=cv2.VideoWriter(str(video_path),cv2.VideoWriter_fourcc(*'mp4v'),cap.get(5),size)
    if not writer.isOpened():raise ValueError('Cannot create identity playback')
    started=time.perf_counter()
    status=json.loads(_status_path(job_id).read_text())
    ids=set();mapping={};observations=0
    try:
        with (directory/'analysis.identity.jsonl').open('w') as sink:
            for r in records:
                ok,frame=cap.read()
                if not ok:raise ValueError('Video ended before detections')
                objects=identity.update(r['objects'],frame,r['frame'],r['timestamp_s'],r.get('scene_cut',False))
                combined={**r,'objects':objects,'unobserved_swimmers':visibility.update(objects,r['timestamp_s'],r.get('scene_cut',False))}
                for before,after in zip(r['objects'],objects):
                    if before['class']!='swimmer':assert before==after
                    else:
                        for key in ('class','confidence','bbox_xyxy_px','distress_action'):
                            assert before.get(key)==after.get(key)
                        mapping.setdefault(str(after['source_track_id']),set()).add(after['track_id'])
                sink.write(json.dumps(combined)+'\n')
                writer.write(render_analysis_frame(frame,combined))
                ids.update(o['track_id'] for o in objects);observations+=len(objects)
    finally:
        cap.release();writer.release()
    (directory/'analysis.identity.jsonl').replace(directory/'analysis.jsonl')
    video_path.replace(directory/'analysis.mp4')
    metadata=json.loads((directory/'swimmer_actions.meta.json').read_text())
    metadata.update(unique_tracks=len(ids),tracked_observations=observations,
                    swimmer_identity={'max_gap_seconds':identity.max_gap,'recoveries':identity.recoveries,
                                      'source_id_mapping':{k:sorted(v) for k,v in mapping.items()}})
    (directory/'swimmer_actions.meta.json').write_text(json.dumps(metadata))
    report=analyze_distress(source,directory/'analysis.jsonl',directory/'distress.json',
                           actions_path=directory/'swimmer_actions.jsonl',classifier_metadata=metadata)
    prepare_playback(directory/'analysis.mp4',directory/'playback.identity.mp4')
    (directory/'playback.identity.mp4').replace(directory/'playback.mp4')
    assert hashlib.sha256((directory/'tracks.jsonl').read_bytes()).hexdigest()==primary_digest
    status['enrichment']=metadata
    elapsed=status['summary']['processing_seconds']+time.perf_counter()-started
    status['summary'].update(unique_tracks=len(ids),tracked_observations=observations,processing_seconds=elapsed,
                             processing_fps=len(records)/elapsed)
    _save_status(job_id,status)
    print(json.dumps({'job':job_id,'primary_tracks_unchanged':True,'source_id_mapping':{k:sorted(v) for k,v in mapping.items()},
                      'warnings':report['events']}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('job_id');args=parser.parse_args()
    restitch(args.job_id)
