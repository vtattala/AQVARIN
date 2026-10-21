"""Live-only multi-scale search, including swimmers missed by identification."""
import time
import hashlib
import json
from pathlib import Path
import shutil

from .action_yolo import ActionModels, LABELS
from .config import ROOT
from .distress import box_iou


def search_tiles(width,height,size=512):
    def positions(length):
        if length <= size: return [0]
        return sorted(set([*range(0,length-size+1,384),length-size]))
    return [(x,y,min(width,x+size),min(height,y+size)) for y in positions(height) for x in positions(width)]


class LiveActionModels(ActionModels):
    def __init__(self,device='cpu',candidate_path=None):
        super().__init__(device)
        settings=ROOT/'config/live-model.local.json'
        config=json.loads(settings.read_text()) if candidate_path is None and settings.is_file() else {}
        self.model_source='imported_checkpoint'
        source=Path(candidate_path or config['weights']) if candidate_path or config.get('enabled') else None
        if source:
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            if not candidate_path and digest!=config['sha256']:
                self.close();raise ValueError('Live camera checkpoint verification failed')
            from ultralytics import YOLO
            target=Path(self.temporary.name)/'camera-candidate.pt';shutil.copy2(source,target)
            self.action=YOLO(str(target))
            if self.action.names!=LABELS:
                self.close();raise ValueError('Live checkpoint class mapping differs')
            self.model_source='camera_adapted_checkpoint'
        self.search_cursor = 0
        self.last_search = -1.

    def predict(self,frame,objects,crop_limit=None):
        proposals,humans,boats = super().predict(frame,objects,crop_limit)
        # The imported checkpoint was trained at 640. A portrait camera frame
        # can lose the same drowning person at 1280 yet detect them strongly at
        # 640. Preserve full-image context at all three scales. These proposals
        # share one inference timestamp later; resolutions never become votes.
        full=list(proposals)
        for size in (640,960):
            result=self.action.predict(frame,conf=.4,imgsz=size,device=self.device,verbose=False)[0]
            for b in result.boxes:
                cls=int(b.cls.item())
                full.append({'class':'swim' if cls==2 else 'drown','label':self.action.names[cls],
                             'score':float(b.conf.item()),'bbox_xyxy_px':[float(v) for v in b.xyxy[0]],
                             'evidence_source':'full_frame_multiscale','inference_size':size})
        proposals=[]
        for proposal in sorted(full,key=lambda p:p['score'],reverse=True):
            if not any(box_iou(proposal['bbox_xyxy_px'],p['bbox_xyxy_px'])>.5 for p in proposals):
                proposals.append(proposal)
        # Independently search the image, rather than requiring an above-water
        # maritime detection to exist before looking for a drowning swimmer.
        # CUDA batches all tiles. CPU rotates two tiles to bound added latency.
        now = time.monotonic()
        if now-self.last_search < 1:
            return proposals,humans,boats
        self.last_search = now
        tiles = search_tiles(frame.shape[1],frame.shape[0])
        budget=6 if str(self.device).startswith('cuda') else 2
        if len(tiles)>budget:
            tiles = [tiles[(self.search_cursor+i)%len(tiles)] for i in range(budget)]
            self.search_cursor += budget
        crops = [frame[y1:y2,x1:x2] for x1,y1,x2,y2 in tiles]
        results = self.action.predict(crops,conf=.5,imgsz=960,device=self.device,verbose=False)
        searched=[]
        for result,(x1,y1,_,_) in zip(results,tiles):
            for b in result.boxes:
                box = [float(v)+offset for v,offset in zip(b.xyxy[0],(x1,y1,x1,y1))]
                label = self.action.names[int(b.cls.item())]
                searched.append({'class':'swim' if int(b.cls.item())==2 else 'drown',
                                  'label':label,'score':float(b.conf.item()),'bbox_xyxy_px':box,
                                  'crop_track_id':None,'evidence_source':'search_tile'})
        for proposal in sorted(searched,key=lambda p:p['score'],reverse=True):
            overlapping=[p for p in proposals if box_iou(proposal['bbox_xyxy_px'],p['bbox_xyxy_px'])>=.3]
            # Preserve existing full-frame drowning evidence. New crop-only
            # evidence retains the stricter five-prediction warning policy.
            if any(p['class']==proposal['class'] or p['class']=='drown' for p in overlapping):
                continue
            if any(p['class']=='swim' and p['score']>=.85 for p in overlapping) and proposal['score']<.95:
                continue
            proposals.append(proposal)
        return proposals,humans,boats
