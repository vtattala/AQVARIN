"""Bounded live-only contextual search around the unchanged RipScout model.

Whole-frame inference always runs. Camera framing can make a plume too small
for its 300 px input, so a rotating set of overlapping views also searches the
image. Different views of one camera frame never supply extra temporal votes.
"""
import math

from .distress import box_iou
from .rip_current import RipScoutModel, RipEvidence


def context_windows(width, height):
    """General scene crops; no clip names, fixed target coordinates or labels."""
    windows = []
    for scale in (.75, .5):
        w, h = round(width*scale), round(height*scale)
        windows += [(x,y,x+w,y+h) for x,y in (
            (0,0),(width-w,0),((width-w)//2,(height-h)//2),
            (0,height-h),(width-w,height-h))]
    # A landscape scene inside a portrait camera image needs wider context
    # than square crops. Overlap ensures coverage between crop boundaries.
    if height > width:
        h = max(64, round(width/2.4))
        count = max(2, math.ceil((height-h)/(h*.5))+1)
        windows += [(0,round(i*(height-h)/(count-1)),width,
                     round(i*(height-h)/(count-1))+h) for i in range(count)]
    return list(dict.fromkeys(windows))


class LiveRipScoutModel:
    def __init__(self, model=None, crop_budget=3):
        self.model = model or RipScoutModel()
        self.crop_budget = max(0,min(3,crop_budget))
        self.reset()

    def reset(self):
        self.shape = None
        self.cursor = 0
        self.index = 0
        self.focus = {}
        self.checked = {}
        self.last_diagnostics = {}

    def predict(self, frame):
        height,width = frame.shape[:2]
        if self.shape != (height,width):
            self.reset()
            self.shape = (height,width)
        full = [{**r,'evidence_source':'full_frame'} for r in self.model.predict(frame)]
        windows = context_windows(width,height)
        # Recheck promising context on NEW frames, and continue independent
        # search. Expire it after four misses; never reuse a cached prediction.
        self.focus = {w:v for w,v in self.focus.items() if self.index-v[0] <= 4}
        focused = sorted(self.focus,key=lambda w:(self.focus[w][0],self.focus[w][1]),reverse=True)
        # At most one follow-up view. At the normal budget, two slots always
        # advance the scene-wide search even when many existing regions persist.
        chosen = focused[:min(1,max(0,self.crop_budget-2))]
        followup_count = len(chosen)
        for _ in range(len(windows)):
            if len(chosen) >= self.crop_budget:
                break
            window = windows[self.cursor % len(windows)]
            self.cursor += 1
            if window not in chosen:
                chosen.append(window)
        crops = []
        for window in chosen:
            self.checked[window] = self.index
            x1,y1,x2,y2 = window
            predictions = self.model.predict(frame[y1:y2,x1:x2])
            if predictions:
                self.focus[window] = (self.index,max(r['score'] for r in predictions))
            for r in predictions:
                bx1,by1,bx2,by2 = r['bbox_xyxy_px']
                crops.append({**r,'bbox_xyxy_px':[bx1+x1,by1+y1,bx2+x1,by2+y1],
                              'evidence_source':'context_crop','context_xyxy_px':list(window)})
        # Preserve whole-frame predictions. Overlapping crop views cannot make
        # duplicate regions or inflate a full-frame model score.
        regions = list(full)
        for candidate in sorted(crops,key=lambda r:r['score'],reverse=True):
            if not any(box_iou(candidate['bbox_xyxy_px'],r['bbox_xyxy_px']) >= .4 for r in regions):
                regions.append(candidate)
        self.last_diagnostics = {'full_frame_predictions':len(full),
            'crop_predictions':len(crops),'crop_passes':len(chosen),
            'search_windows':len(windows),'regions':len(regions),
            'scope':'visible sediment-plume candidates','threshold':.5,
            'context_search_enabled':self.crop_budget>0,
            'coverage':{'views_checked':len(self.checked),'total_views':len(windows),
                        'oldest_view_age_frames':max(self.index-i for i in self.checked.values())
                            if len(self.checked)==len(windows) else None,
                        'discovery_slots':self.crop_budget-followup_count},
            'views':[list(w) for w in chosen]}
        self.index += 1
        return regions


class LiveRipEvidence(RipEvidence):
    def __init__(self):
        super().__init__(window_seconds=6,max_gap_seconds=2.5)

    def warning_ready(self, track, timestamp):
        if not super().warning_ready(track,timestamp):
            return False
        # Wider search increases the number of views. Crop-only evidence needs
        # a stronger peak; ordinary full-frame behavior stays unchanged.
        return (any(s=='full_frame' for s in track['sources'].values())
                or max(s for _,s in track['samples']) >= .75)
