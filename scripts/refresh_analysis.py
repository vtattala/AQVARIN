"""Rebuild companion outputs for an existing job; keep primary inference untouched."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from vision.action_yolo import run_video
from vision.api import _save_status, _status_path
from vision.distress import analyze_distress
from vision.playback import prepare_playback


def refresh(job_id, reuse=False):
    path = _status_path(job_id)
    directory = path.parent
    status = json.loads(path.read_text(encoding='utf-8'))
    tracks = directory/'tracks.jsonl'
    digest = hashlib.sha256(tracks.read_bytes()).hexdigest()
    source = next(directory.glob('source.*'))
    started = perf_counter()
    metadata = json.loads((directory/'swimmer_actions.meta.json').read_text()) if reuse else run_video(
        source,tracks,directory/'swimmer_actions.jsonl',directory/'analysis.jsonl',directory/'analysis.mp4')
    report = analyze_distress(source,directory/'analysis.jsonl',directory/'distress.json',
                              actions_path=directory/'swimmer_actions.jsonl',classifier_metadata=metadata)
    prepare_playback(directory/'analysis.mp4',directory/'playback.mp4')
    if hashlib.sha256(tracks.read_bytes()).hexdigest() != digest:
        raise AssertionError('Primary tracks changed')
    if not (directory/'status.before_actions.json').exists():
        (directory/'status.before_actions.json').write_text(json.dumps(status),encoding='utf-8')
    baseline = status.get('identification_summary',status['summary'])
    elapsed = baseline['processing_seconds'] + perf_counter()-started
    status.update(identification_summary=baseline,enrichment=metadata,distress_status='complete')
    status['summary'] = dict(baseline,tracked_observations=metadata['tracked_observations'],
                             unique_tracks=metadata['unique_tracks'],processing_seconds=elapsed,
                             processing_fps=baseline['frames']/elapsed,output_video=str(directory/'analysis.mp4'),
                             output_jsonl=str(directory/'analysis.jsonl'))
    _save_status(job_id,status)
    print(json.dumps({'job_id':job_id,'primary_tracks_unchanged':True,'classifier':metadata,'review_events':len(report['events'])}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('job_id')
    parser.add_argument('--reuse-actions',action='store_true')
    args = parser.parse_args()
    refresh(args.job_id,args.reuse_actions)
