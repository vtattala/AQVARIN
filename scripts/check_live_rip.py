"""Compare original and live RipScout on a file, including portrait framing.

This is a reproducible camera-framing regression, not a physical camera test
or an independently labeled evaluation of current location/flow.
"""
import argparse
import hashlib
import json
import time
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

from vision.live_rip import LiveRipScoutModel, LiveRipEvidence
from vision.rip_current import RipScoutModel, RipEvidence


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('--seconds',type=float,default=19)
    parser.add_argument('--portrait',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    original=hashlib.sha256(args.source.read_bytes()).hexdigest()
    model=RipScoutModel();live=LiveRipScoutModel()
    old_evidence=RipEvidence(window_seconds=6,max_gap_seconds=2.5);new_evidence=LiveRipEvidence()
    capture=cv2.VideoCapture(str(args.source));rows=[];durations=[]
    try:
        for sequence,timestamp in enumerate(np.arange(0,args.seconds,.4)):
            capture.set(cv2.CAP_PROP_POS_MSEC,float(timestamp*1000))
            ok,frame=capture.read()
            if not ok:break
            scale=min(1,1280/max(frame.shape[:2]))
            frame=cv2.resize(frame,(round(frame.shape[1]*scale),round(frame.shape[0]*scale)))
            if args.portrait:
                # Preserve source aspect ratio, with dark margins as when a
                # wide scene is filmed inside a portrait camera view.
                height=round(672*frame.shape[0]/frame.shape[1])
                canvas=np.full((1280,720,3),18,np.uint8)
                top=(1280-height)//2
                canvas[top:top+height,24:696]=cv2.resize(frame,(672,height))
                frame=canvas
            previous=old_evidence.update(model.predict(frame),sequence,float(timestamp))
            start=time.perf_counter()
            current=new_evidence.update(live.predict(frame),sequence,float(timestamp))
            durations.append((time.perf_counter()-start)*1000)
            rows.append({'timestamp_s':float(timestamp),'baseline_regions':previous,'live_regions':current,
                         'rip_diagnostics':live.last_diagnostics})
    finally:capture.release()
    assert hashlib.sha256(args.source.read_bytes()).hexdigest()==original
    report={'source':str(args.source),'source_sha256':original,'portrait_fixture':args.portrait,
            'physical_camera_test':False,'baseline_events':old_evidence.events,'live_events':new_evidence.events,
            'median_rip_ms':float(np.median(durations)),'samples':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='samples'},indent=2),flush=True)


if __name__=='__main__':main()
