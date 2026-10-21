"""Exercise the running live API using timestamped frames, with no upload jobs.

This checks transport and real models using a saved clip as a deterministic
camera substitute. It does not claim to test physical camera permissions.
"""
import argparse
import base64
import hashlib
import json
import time
from pathlib import Path
from urllib.request import Request, ProxyHandler, build_opener

import cv2


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('--server',default='http://127.0.0.1:8000')
    parser.add_argument('--frames',type=int,default=8)
    parser.add_argument('--output',type=Path,default=Path('outputs/live-validation/http-stream.json'))
    args=parser.parse_args()
    opener=build_opener(ProxyHandler({}))
    def call(path,body=None,headers=None,method=None):
        with opener.open(Request(args.server+path,data=body,headers=headers or {},method=method),timeout=90) as response:
            return json.loads(response.read() or b'null')
    before=hashlib.sha256(args.source.read_bytes()).hexdigest()
    started=time.perf_counter()
    session=call('/api/live/sessions',b'{"scene_type":"auto"}',{'Content-Type':'application/json'})
    print('Started',session['session_id'],session['models'],'load seconds',round(time.perf_counter()-started,2),flush=True)
    key=session['session_id'];capture=cv2.VideoCapture(str(args.source));rows=[]
    try:
        fps=capture.get(cv2.CAP_PROP_FPS)
        duration=capture.get(cv2.CAP_PROP_FRAME_COUNT)/fps
        started=time.perf_counter()
        for sequence in range(args.frames):
            # Advance by wall time to mimic newest-frame capture rather than a queue.
            now=time.perf_counter()-started
            if now>=duration:break
            capture.set(cv2.CAP_PROP_POS_FRAMES,int(now*fps))
            ok,frame=capture.read()
            if not ok:break
            scale=min(1,1280/max(frame.shape[:2]))
            frame=cv2.resize(frame,(round(frame.shape[1]*scale),round(frame.shape[0]*scale)))
            jpeg=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,85])[1].tobytes()
            tick=time.perf_counter()
            result=call(f'/api/live/sessions/{key}/frame',jpeg,{'Content-Type':'image/jpeg',
                'X-Frame-Sequence':str(sequence),'X-Captured-At':str(now)})
            assert result['sequence']==sequence and result['captured_at_s']==now
            assert result['tracking']['timestamp_s']==now
            image=base64.b64decode(result.pop('image_base64'))
            result['round_trip_ms']=round((time.perf_counter()-tick)*1000,1)
            rows.append(result)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.with_suffix('.jpg').write_bytes(image)
            print('Frame',sequence,'seconds',round(now,2),'processing ms',result['processing_ms'],
                  'round trip ms',result['round_trip_ms'],'objects',len(result['tracking']['objects']),
                  'drowning warnings',len(result['distress_events']),'rip warnings',len(result['rip_events']),flush=True)
    finally:
        capture.release();call(f'/api/live/sessions/{key}',method='DELETE')
    assert hashlib.sha256(args.source.read_bytes()).hexdigest()==before
    args.output.write_text(json.dumps(rows,indent=2),encoding='utf-8')
    print('Stream stopped; source unchanged.',flush=True)


if __name__=='__main__':main()
