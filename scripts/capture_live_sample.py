"""Explicit, bounded local export for a user-requested camera debugging replay."""
import argparse
import json
from pathlib import Path
import re
import time
from urllib.request import build_opener, ProxyHandler

ROOT=Path(__file__).resolve().parent.parent


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--seconds',type=float,default=15)
    parser.add_argument('--wait-seconds',type=float,default=120)
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/live-refinement/phone-sample')
    args=parser.parse_args()
    if not 0<args.seconds<=30:raise SystemExit('Sample must be 1–30 seconds')
    opener=build_opener(ProxyHandler({}));key=None;deadline=time.monotonic()+min(600,args.wait_seconds)
    print('Waiting for an active camera session for the requested pool test.',flush=True)
    while key is None and time.monotonic()<deadline:
        log=(ROOT/'outputs/server-logs/api.log').read_text(encoding='utf-8',errors='replace')
        matches=re.findall(r'/api/live/sessions/([a-f0-9-]{36})/frame',log)
        if matches:
            candidate=matches[-1]
            try:
                if re.search(r'DELETE /api/live/sessions/'+candidate,log[log.rfind('/api/live/sessions/'+candidate+'/frame'):]):
                    time.sleep(2);continue
                with opener.open('http://127.0.0.1:8000/api/live/sessions/'+candidate+'/diagnostics',timeout=3) as response:
                    rows=json.loads(response.read())
                    if rows and rows[-1].get('client_kind')=='camera':key=candidate
            except Exception:pass
        if key is None:time.sleep(2)
    if key is None:raise SystemExit('No active camera test session started')
    args.output.mkdir(parents=True,exist_ok=True)
    seen=set();metadata=[];started=time.monotonic()
    while time.monotonic()-started<args.seconds:
        base='http://127.0.0.1:8000/api/live/sessions/'+key
        try:
            with opener.open(base+'/diagnostic-frame',timeout=5) as response:
                sequence=int(response.headers['X-Frame-Sequence']);captured=float(response.headers['X-Captured-At']);data=response.read()
            if sequence not in seen:
                (args.output/f'frame-{sequence:05d}.jpg').write_bytes(data);seen.add(sequence)
                metadata.append({'sequence':sequence,'captured_at_s':captured})
            with opener.open(base+'/diagnostics',timeout=5) as response:rows=json.loads(response.read())
            (args.output/'diagnostics.json').write_text(json.dumps(rows,indent=2))
        except Exception as exc:print(str(exc),flush=True);break
        time.sleep(.4)
    (args.output/'frames.json').write_text(json.dumps(metadata,indent=2))
    print(f'Exported {len(seen)} test frames to {args.output}; no audio.',flush=True)


if __name__=='__main__':main()
