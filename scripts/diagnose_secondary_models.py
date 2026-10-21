"""Inspect trained companion predictions on saved jobs without changing results."""
import json
import os
from pathlib import Path
import cv2
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
models = {
    'drowning': YOLO('third_party/drowning-detection-system/models/drowning_detection_yolov8/weights/best.pt'),
    'general': YOLO('third_party/drowning-detection-system/models/yolov8n.pt'),
}
print('LABELS', {name: m.names for name,m in models.items() if name == 'drowning'})
output = ROOT/'outputs/diagnosis_oct09'
for job in ('3b0cd383-69ea-45ff-9374-a8a1e131ba79','451b8ab0-10f3-4599-a4fb-c0fdbdae99f1'):
    directory = ROOT/'outputs/jobs'/job
    cap = cv2.VideoCapture(str(next(directory.glob('source.*'))))
    tracks = [json.loads(l) for l in (directory/'tracks.jsonl').read_text().splitlines()]
    for frame_id in (0, 30, 60, 100, 150, 250, 350):
        cap.set(1,frame_id)
        ok, frame = cap.read()
        if not ok:
            continue
        for name, model in models.items():
            result = model.predict(frame, conf=.15, imgsz=1280, device='cpu', verbose=False,
                                   classes=[0,8] if name=='general' else None)[0]
            predictions = [{'class':model.names[int(b.cls.item())], 'score':round(float(b.conf.item()),3),
                            'box': [round(float(x)) for x in b.xyxy[0]]} for b in result.boxes]
            print(json.dumps({'job':job,'frame':frame_id,'model':name,'predictions':predictions,
                              'base':[(o['class'],round(o['confidence'],2),o['bbox_xyxy_px']) for o in tracks[frame_id]['objects']]}))
            cv2.imwrite(str(output/f'{job}_{frame_id}_{name}.jpg'), result.plot())
    cap.release()
