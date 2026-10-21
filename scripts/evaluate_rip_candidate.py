"""Offline candidate gate; never activates/replaces an application model."""
import argparse
import hashlib
import json
import shutil
import tempfile
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

from vision.live_runtime import activate_live_runtime
from vision.rip_current import RipEvidence


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('weights',type=Path)
    parser.add_argument('--source',action='append',required=True,help='Label=path')
    parser.add_argument('--seconds',type=float,default=19)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    activate_live_runtime()
    import torch
    from ultralytics import YOLO
    torch.set_num_threads(4)
    reports=[]
    with tempfile.TemporaryDirectory(prefix='aqvarin-rip-eval-') as staging:
        weights=Path(staging)/'candidate.pt';shutil.copy2(args.weights,weights)
        model=YOLO(str(weights));print('Model',model.task,model.names,flush=True)
        for entry in args.source:
            label,source=entry.split('=',1);source=Path(source)
            for portrait in ([False,True] if label=='rip' else [False]):
                capture=cv2.VideoCapture(str(source));rows=[]
                evidence=RipEvidence(window_seconds=6,max_gap_seconds=2.5)
                try:
                    for sequence,timestamp in enumerate(np.arange(0,args.seconds,.5)):
                        capture.set(cv2.CAP_PROP_POS_MSEC,float(timestamp*1000));ok,frame=capture.read()
                        if not ok:break
                        scale=min(1,1280/max(frame.shape[:2]));frame=cv2.resize(frame,(round(frame.shape[1]*scale),round(frame.shape[0]*scale)))
                        if portrait:
                            height=round(672*frame.shape[0]/frame.shape[1]);top=(1280-height)//2
                            canvas=np.full((1280,720,3),18,np.uint8);canvas[top:top+height,24:696]=cv2.resize(frame,(672,height));frame=canvas
                        result=model.predict(frame,imgsz=640,conf=.5,device=0,verbose=False)[0]
                        regions=[]
                        detections=result.obb if model.task=='obb' else result.boxes
                        if detections is not None:
                            for box,score,cls in zip(detections.xyxy.cpu().tolist(),detections.conf.cpu().tolist(),detections.cls.cpu().tolist()):
                                regions.append({'label':str(model.names[int(cls)]),'score':score,'bbox_xyxy_px':box})
                        evidence.update(regions,sequence,float(timestamp));rows.append({'timestamp_s':float(timestamp),'regions':regions})
                finally:capture.release()
                report={'label':label,'source':str(source),'portrait':portrait,'samples':rows,'events':evidence.events,
                        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
                reports.append(report)
                args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(reports,indent=2))
                print(label,'portrait',portrait,'positive frames',sum(bool(r['regions']) for r in rows),'events',len(evidence.events),flush=True)


if __name__=='__main__':main()
