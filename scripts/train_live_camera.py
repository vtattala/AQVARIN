"""Train a separate camera-domain candidate; never replaces imported checkpoints.

Uses only the upstream labeled train split with synthetic camera degradation.
Validation/test splits remain untouched. Enabling a candidate is a separate step.
"""
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import time

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parent.parent


def camera_variant(image,labels,rng):
    h,w=image.shape[:2]
    # Perspective and framing vary independently of class and source filename.
    source=np.float32([[0,0],[w,0],[w,h],[0,h]])
    target=source+np.array([[rng.uniform(-.06,.06)*w,rng.uniform(-.06,.06)*h] for _ in range(4)],np.float32)
    matrix=cv2.getPerspectiveTransform(source,target)
    frame=cv2.warpPerspective(image,matrix,(w,h),borderMode=cv2.BORDER_REFLECT_101)
    transformed=[]
    for row in labels:
        cls,x,y,bw,bh=row
        corners=np.float32([[(x-bw/2)*w,(y-bh/2)*h],[(x+bw/2)*w,(y-bh/2)*h],
                            [(x+bw/2)*w,(y+bh/2)*h],[(x-bw/2)*w,(y+bh/2)*h]])
        projected=cv2.perspectiveTransform(corners[None],matrix)[0]
        x1,y1=np.maximum(projected.min(axis=0),0);x2,y2=np.minimum(projected.max(axis=0),(w,h))
        if x2-x1>=4 and y2-y1>=4:transformed.append([int(cls),(x1+x2)/2/w,(y1+y2)/2/h,(x2-x1)/w,(y2-y1)/h])
    scale=rng.uniform(.4,.85)
    frame=cv2.resize(cv2.resize(frame,(max(16,round(w*scale)),max(16,round(h*scale)))),(w,h))
    if rng.random()<.7:frame=cv2.GaussianBlur(frame,(3,3),rng.uniform(.3,1.1))
    gain=rng.uniform(.75,1.2);offset=rng.uniform(-18,18)
    frame=np.clip(frame.astype(np.float32)*gain+offset,0,255).astype(np.uint8)
    noise=np.random.default_rng(rng.randrange(2**32)).normal(0,rng.uniform(0,3),frame.shape)
    frame=np.clip(frame.astype(np.float32)+noise,0,255).astype(np.uint8)
    encoded=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,rng.randint(55,90)])[1]
    return encoded,transformed


def main():
    import torch
    stage=(Path(os.environ['LOCALAPPDATA'])/'Aqvarin/live-training').resolve()
    (stage/'ultralytics-settings').mkdir(parents=True,exist_ok=True)
    os.environ['YOLO_CONFIG_DIR']=str(stage/'ultralytics-settings')
    from ultralytics import YOLO, settings
    assert torch.cuda.is_available(),'Run with the isolated live GPU Python'
    torch.set_num_threads(4)
    settings.update({k:False for k in ['wandb','mlflow','comet','clearml','neptune','hub'] if k in settings})
    os.environ['WANDB_MODE']='disabled'
    dataset=stage/'data';dataset.mkdir(parents=True,exist_ok=True)
    upstream=ROOT/'third_party/drowning-detection-system/data'
    for split in ['train','valid','test']:
        shutil.copytree(upstream/split,dataset/split,dirs_exist_ok=True,ignore=shutil.ignore_patterns('*.cache'))
    rng=random.Random(20261020)
    for image in sorted((upstream/'train/images').glob('*')):
        frame=cv2.imread(str(image));label=upstream/'train/labels'/(image.stem+'.txt')
        rows=[[float(v) for v in line.split()] for line in label.read_text().splitlines() if line.strip()]
        encoded,rows=camera_variant(frame,rows,rng)
        (dataset/'train/images'/('camera_'+image.stem+'.jpg')).write_bytes(encoded.tobytes())
        (dataset/'train/labels'/('camera_'+image.stem+'.txt')).write_text('\n'.join(' '.join(map(str,row)) for row in rows))
    yaml=dataset/'data.yaml'
    yaml.write_text('path: '+dataset.as_posix()+'\ntrain: train/images\nval: valid/images\ntest: test/images\nnames: [Active drowning, Possible Passive Drowner, Swimming]\n')
    weights=stage/'upstream.pt';shutil.copy2(ROOT/'assets/models/drowning_yolov8n.pt',weights)
    model=YOLO(str(weights))
    baseline=model.val(data=str(yaml),split='test',imgsz=640,batch=16,device=0,workers=0,plots=False,
                       project=str(stage/'runs'),name='baseline-test',exist_ok=True)
    before=dict(baseline.results_dict)
    started=time.monotonic()
    model.train(data=str(yaml),epochs=15,imgsz=640,batch=16,device=0,workers=0,seed=20261020,
                deterministic=True,project=str(stage/'runs'),name='camera-candidate',exist_ok=True,
                pretrained=True,amp=True,plots=False,save=True,patience=15,
                degrees=8,translate=.15,scale=.65,perspective=.0005,mosaic=.5,close_mosaic=4,
                hsv_h=.015,hsv_s=.4,hsv_v=.3,fliplr=.5,flipud=0,cache=False)
    best=stage/'runs/camera-candidate/weights/best.pt'
    tested=YOLO(str(best)).val(data=str(yaml),split='test',imgsz=640,batch=16,device=0,workers=0,
                               plots=False,project=str(stage/'runs'),name='candidate-test',exist_ok=True)
    output=ROOT/'outputs/live-refinement/training';output.mkdir(parents=True,exist_ok=True)
    candidate=output/'camera-candidate.pt';shutil.copy2(best,candidate)
    manifest={'enabled':False,'source':'upstream labeled training split only; plus seeded camera augmentations',
              'upstream_repository':'https://github.com/yashpotdar-py/drowning-detection-system',
              'upstream_revision':'21174a740fe9461af87183e8f96f34ca78f3fcdc','dataset_license':'CC BY 4.0',
              'baseline_test':before,'candidate_test':dict(tested.results_dict),'epochs':15,
              'training_seconds':time.monotonic()-started,'sha256':hashlib.sha256(candidate.read_bytes()).hexdigest(),
              'caveat':'Upstream test split is not independent field validation. Camera replay and negative regressions required before activation.'}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2),flush=True)


if __name__=='__main__':main()
