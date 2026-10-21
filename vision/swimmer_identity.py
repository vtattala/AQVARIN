"""Conservative swimmer ID continuity over short occlusions, separate from detection."""
import copy
import math
import numpy as np
from .history import TrackHistory
from .models import Detection


class SwimmerIdentity:
    def __init__(self, reserved_ids=(), first_id=1, max_gap_s=8):
        self.reserved = set(reserved_ids)
        self.next_id = first_id
        self.used = set()
        self.tracks = {}
        self.aliases = {}
        self.history = TrackHistory(300,10)
        self.max_gap = max_gap_s
        self.previous_gray = None
        self.recoveries = []

    @staticmethod
    def geometry(box):
        return np.array([(box[0]+box[2])/2,(box[1]+box[3])/2]), max(8,math.sqrt(max(1,(box[2]-box[0])*(box[3]-box[1]))))

    @staticmethod
    def appearance(frame, box):
        import cv2
        x1,y1,x2,y2 = [int(v) for v in box]
        crop = frame[max(0,y1):min(frame.shape[0],y2),max(0,x1):min(frame.shape[1],x2)]
        if not crop.size:
            return None
        hsv = cv2.cvtColor(cv2.resize(crop,(32,48)),cv2.COLOR_BGR2HSV)
        # Suppress blue water/tubes; use visible skin, hair and clothing colors.
        mask = (((hsv[:,:,0]<85) | (hsv[:,:,0]>135)) & (hsv[:,:,1]>25)) | ((hsv[:,:,2]<90) & (hsv[:,:,1]<90))
        if mask.sum()<24:
            return None
        hist = cv2.calcHist([hsv],[0,1],mask.astype('uint8')*255,[12,8],[0,180,0,256]).reshape(-1)
        return hist/max(1,np.linalg.norm(hist))

    def camera_motion(self, frame):
        import cv2
        height,width = frame.shape[:2]
        scale = min(1,640/width)
        gray = cv2.resize(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),(round(width*scale),round(height*scale)))
        previous,self.previous_gray = self.previous_gray,gray
        if previous is None or previous.shape!=gray.shape:
            return
        points = cv2.goodFeaturesToTrack(previous,150,.02,12)
        if points is None or len(points)<12:
            return
        moved,status,_ = cv2.calcOpticalFlowPyrLK(previous,gray,points,None)
        if moved is None:
            return
        good = status.reshape(-1).astype(bool)
        if good.sum()<12:
            return
        matrix,inliers = cv2.estimateAffinePartial2D(points[good],moved[good],method=cv2.RANSAC,ransacReprojThreshold=2)
        if matrix is None or inliers.sum()<12 or not .95<np.linalg.norm(matrix[:,0])<1.05:
            return
        matrix[:,2]/=scale
        for track in self.tracks.values():
            box = track['box']
            corners = np.array([[box[0],box[1]],[box[2],box[1]],[box[0],box[3]],[box[2],box[3]]])
            corners = corners@matrix[:,:2].T+matrix[:,2]
            track['box'] = [float(corners[:,0].min()),float(corners[:,1].min()),float(corners[:,0].max()),float(corners[:,1].max())]
            track['velocity'] = matrix[:,:2]@track['velocity']

    def cost(self, track, obj, descriptor, now):
        gap = now-track['time']
        center,size = self.geometry(track['box'])
        new_center,new_size = self.geometry(obj['bbox_xyxy_px'])
        ratio = new_size/size
        if not .4<=ratio<=2.5:
            return 100.
        predicted = center+track['velocity']*min(gap,1)
        distance = np.linalg.norm(new_center-predicted)/math.sqrt(size*new_size)
        if distance>1.6 or (gap>.5 and np.linalg.norm(new_center-center)/min(size,new_size)>1.6):
            return 100.
        appearance = 0.
        if descriptor is not None and track['appearance'] is not None:
            appearance = max(0.,1-float(descriptor@track['appearance']))
            if appearance>.8:
                return 100.
        return float(distance+.2*abs(math.log(ratio))+.35*appearance)

    def update(self, objects, frame, frame_number, now, scene_cut=False):
        import lap
        if scene_cut:
            self.tracks.clear();self.aliases.clear()
            self.history = TrackHistory(300,10)
            self.previous_gray = None
        self.camera_motion(frame)
        self.tracks = {tid:v for tid,v in self.tracks.items() if now-v['time']<=self.max_gap}
        swimmers = [o for o in objects if o['class']=='swimmer']
        descriptors = [self.appearance(frame,o['bbox_xyxy_px']) for o in swimmers]
        ids = list(self.tracks)
        costs = np.full((len(ids),len(swimmers)),100.)
        for i,tid in enumerate(ids):
            for j,o in enumerate(swimmers):
                cost = self.cost(self.tracks[tid],o,descriptors[j],now)
                raw = o.get('source_track_id',o['track_id'])
                if self.aliases.get(raw)==tid and ((now-self.tracks[tid]['time']<=.5 and cost<1) or cost<.65):
                    cost-=.3
                costs[i,j] = cost
        assignments = {}
        if costs.size:
            _,matches,_ = lap.lapjv(costs,extend_cost=True,cost_limit=1.25)
            for i,j in enumerate(matches):
                if j<0:
                    continue
                tid = ids[i]
                gap = now-self.tracks[tid]['time']
                raw = swimmers[j].get('source_track_id',swimmers[j]['track_id'])
                continuous = self.aliases.get(raw)==tid and (gap<=.5 or costs[i,j]<.35)
                alternatives = [costs[k,j] for k in range(len(ids)) if k!=i]
                rivals = [costs[i,k] for k in range(len(swimmers)) if k!=j]
                if not continuous and (min(alternatives or [100])-costs[i,j]<.2 or min(rivals or [100])-costs[i,j]<.2):
                    continue  # Do not merge an ambiguous neighbor/crossing.
                assignments[j] = tid
        out = []
        for j,obj in enumerate(swimmers):
            raw = obj.get('source_track_id',obj['track_id'])
            tid = assignments.get(j)
            method = 'continuity'
            if tid is None:
                method = 'new'
                tid = raw if raw not in self.used and raw not in self.reserved else self.allocate()
                self.used.add(tid)
            previous = self.tracks.get(tid)
            gap = now-previous['time'] if previous else 0
            if previous and (raw not in previous['sources'] or gap>.5):
                method = 'reacquired'
                self.recoveries.append({'frame':frame_number,'timestamp_s':now,'source_track_id':raw,'track_id':tid,'gap_seconds':gap})
            center,size = self.geometry(obj['bbox_xyxy_px'])
            velocity = np.zeros(2)
            if previous and gap>0 and gap<=.5:
                old_center,_ = self.geometry(previous['box'])
                measured = (center-old_center)/gap
                if np.linalg.norm(measured)<=size*2:
                    velocity = .7*previous['velocity']+.3*measured
            descriptor = descriptors[j]
            if previous and previous['appearance'] is not None and descriptor is not None:
                descriptor = .8*previous['appearance']+.2*descriptor
                descriptor/=max(1e-9,np.linalg.norm(descriptor))
            sources = (previous['sources'] if previous else set()) | {raw}
            self.tracks[tid] = {'box':obj['bbox_xyxy_px'],'time':now,'velocity':velocity,'appearance':descriptor,'sources':sources}
            self.aliases[raw] = tid
            detection = Detection(4,'swimmer',obj['confidence'],tuple(obj['bbox_xyxy_px']))
            history = self.history.update(tid,detection,frame_number,now).to_dict()
            out.append({**copy.deepcopy(obj),**history,'source_track_id':raw,
                        'identity':{'method':method,'gap_seconds':gap}})
        indexed = iter(out)
        return [next(indexed) if o['class']=='swimmer' else copy.deepcopy(o) for o in objects]

    def allocate(self):
        while self.next_id in self.used or self.next_id in self.reserved:
            self.next_id+=1
        value = self.next_id
        self.next_id+=1
        return value
