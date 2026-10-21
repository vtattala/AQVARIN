"""Start both local services and restart them if they exit."""
from pathlib import Path
import argparse
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / 'outputs/server-logs'
PORTS = {'api':8000,'app':8081}
URLS = {'api':'http://127.0.0.1:8000/api/health','app':'http://127.0.0.1:8081/'}

def listening(port):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=1):
            return True
    except OSError:
        return False

def ready(name):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(URLS[name],timeout=3) as response:
            return response.status == 200
    except Exception:
        return False

def supervise(name):
    import msvcrt
    LOGS.mkdir(parents=True,exist_ok=True)
    lock = (LOGS/f'{name}.lock').open('a+b')
    lock.write(b'0'); lock.flush(); lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        lock.close()
        return
    if name == 'api':
        command = [sys.executable,'-m','uvicorn','vision.api:app','--host','0.0.0.0','--port','8000']
        cwd = ROOT
    else:
        node = shutil.which('node.exe')
        if not node:
            raise RuntimeError('Node.js is not available on PATH')
        command = [node,str(ROOT/'mobile/node_modules/expo/bin/cli'),'start','--web','--port','8081']
        cwd = ROOT/'mobile'
    while True:
        # Reuse existing processes without interrupting an active analysis.
        if listening(PORTS[name]):
            time.sleep(2)
            continue
        with (LOGS/f'{name}.log').open('a',encoding='utf-8') as log:
            child = subprocess.Popen(command,cwd=cwd,stdin=subprocess.DEVNULL,stdout=log,
                                     stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            code = child.wait()
            log.write(f'\nService exited ({code}); restarting in 2 seconds.\n')
        time.sleep(2)

def start():
    LOGS.mkdir(parents=True,exist_ok=True)
    for name in PORTS:
        with (LOGS/f'{name}-supervisor.log').open('a',encoding='utf-8') as log:
            subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--service',name],cwd=ROOT,
                             stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic()+90
        while not ready(name):
            if time.monotonic() >= deadline:
                raise RuntimeError(f'{name} is not ready. Check {LOGS}')
            time.sleep(1)
    print('AQVARIN is running: http://localhost:8081/')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--service',choices=list(PORTS))
    args = parser.parse_args()
    if args.service:
        supervise(args.service)
    else:
        start()
