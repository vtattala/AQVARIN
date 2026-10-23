#!/usr/bin/env python3
"""One-time Mac setup: boot-time Pi camera + a reconnecting localhost SSH link.

Run on the Mac, not inside SSH. Requires existing Pi camera packages, SSH login,
and sudo rights on the Pi. No Pi password is stored. --dry-run changes nothing.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

EMBEDDED_CAMERA = None  # Bundled in the standalone deliverable; never includes a token.
LABEL = 'com.aqvarin.pi-camera-link'


def remote_setup(camera, public_key):
    payload = base64.b64encode(json.dumps({'camera': base64.b64encode(camera).decode(), 'key': public_key.strip()}).encode()).decode()
    return '''import base64,json,os,pathlib,pwd,subprocess,time,urllib.request,urllib.error
p=json.loads(base64.b64decode(PAYLOAD))
home=pathlib.Path.home(); user=pwd.getpwuid(os.getuid()).pw_name
# Check prerequisites before touching the running camera or granting access.
subprocess.run(['/usr/bin/python3','-c','import picamera2'],check=True)
subprocess.run(['sudo','-n','true'],check=True)
folder=home/'aqvarin-camera'; folder.mkdir(exist_ok=True)
script=folder/'pi_camera.py'; token=folder/'camera-token.local'
if not token.is_file(): raise SystemExit('Existing camera-token.local missing. Start and pair your Pi camera first.')
key=p['key']
if not key.startswith('ssh-ed25519 ') or '\\n' in key: raise SystemExit('Invalid tunnel public key')
# This key can forward to the camera only; it cannot open a remote shell.
line='restrict,port-forwarding,permitopen="127.0.0.1:8001",permitlisten="127.0.0.1:8001",command="/bin/false" '+key
ssh=home/'.ssh'; ssh.mkdir(mode=0o700,exist_ok=True)
auth=ssh/'authorized_keys'; previous=auth.read_text() if auth.exists() else ''
if line not in previous.splitlines():
    with auth.open('a') as out: out.write(('\\n' if previous and not previous.endswith('\\n') else '')+line+'\\n')
ssh.chmod(0o700); auth.chmod(0o600); token.chmod(0o600)
service='aqvarin-camera.service'
subprocess.run(['sudo','-n','systemctl','stop',service],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
# Stop only the old manual AQVARIN camera owned by this login user.
subprocess.run(['pkill','-u',str(os.getuid()),'-f',r'^([^ ]*/)?python3 ([^ ]*/)?pi_camera[.]py( |$)'],check=False)
time.sleep(2)
script.write_bytes(base64.b64decode(p['camera']))
unit='[Unit]\\nDescription=AQVARIN Pi camera\\nAfter=network.target\\nStartLimitIntervalSec=0\\n\\n[Service]\\nType=simple\\nUser='+user+'\\nWorkingDirectory='+str(folder)+'\\nExecStart=/usr/bin/python3 '+str(script)+' --token-file '+str(token)+'\\nRestart=on-failure\\nRestartSec=5\\nUMask=0077\\n\\n[Install]\\nWantedBy=multi-user.target\\n'
# Raspberry Pi usernames/home paths contain no spaces in this supported setup.
if any(c.isspace() for c in str(folder)) or '%' in str(folder): raise SystemExit('Unsupported home directory path')
unitfile=folder/'aqvarin-camera.service'; unitfile.write_text(unit)
subprocess.run(['sudo','-n','install','-m','644',str(unitfile),'/etc/systemd/system/'+service],check=True)
subprocess.run(['sudo','-n','systemctl','daemon-reload'],check=True)
subprocess.run(['sudo','-n','systemctl','enable','--now',service],check=True)
# Verify authenticated camera readiness; never print the token.
for attempt in range(30):
    try:
        req=urllib.request.Request('http://127.0.0.1:8001/api/camera/health',headers={'Authorization':'Bearer '+token.read_text().strip()})
        with urllib.request.urlopen(req,timeout=3) as response:
            if json.load(response).get('status')=='ready': break
    except (OSError,ValueError,urllib.error.URLError): pass
    time.sleep(1)
else: raise SystemExit('Camera did not become ready. On Pi: sudo journalctl -u aqvarin-camera -n 30')
print('Pi camera verified and enabled at boot.')
'''.replace('PAYLOAD', repr(payload))


def launch_agent(key, host, user, directory):
    return {'Label': LABEL, 'ProgramArguments': [
        '/usr/bin/ssh', '-N', '-T', '-i', str(key), '-o', 'IdentitiesOnly=yes',
        '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
        '-o', 'ExitOnForwardFailure=yes', '-o', 'ConnectTimeout=8',
        '-L', '127.0.0.1:8766:127.0.0.1:8001', f'{user}@{host}'],
        'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 15,
        'StandardOutPath': str(directory/'camera-link.log'),
        'StandardErrorPath': str(directory/'camera-link-error.log')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='aqvarin-pi.local')
    parser.add_argument('--user',default='brian')
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    if sys.platform!='darwin' or os.environ.get('SSH_CONNECTION'):
        parser.error('Run this on your Mac, outside SSH.')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*',args.host) or not re.fullmatch(r'[a-z_][a-z0-9_-]*',args.user):
        parser.error('Use a simple Pi hostname and Linux username.')
    camera=base64.b64decode(EMBEDDED_CAMERA) if EMBEDDED_CAMERA else Path(__file__).with_name('pi_camera.py').read_bytes()
    compile(camera,'pi_camera.py','exec')
    directory=Path.home()/'Library/Application Support/AQVARIN'
    key=directory/'pi-camera-link-ed25519'
    plist=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
    agent=launch_agent(key,args.host,args.user,directory)
    if args.dry_run:
        compile(remote_setup(camera,'ssh-ed25519 AAAA dry-run'),'remote_setup','exec')
        plistlib.loads(plistlib.dumps(agent))
        print('Dry run: no changes.\nPi: install camera systemd service; preserve token; add camera-only SSH key.\nMac: create dedicated SSH key and login-time reconnecting camera link.\nCamera address: http://127.0.0.1:8766\nPi login: '+args.user+'@'+args.host)
        return
    # Avoid replacing any process already listening at the chosen port.
    with socket.socket() as probe:
        probe.settimeout(1)
        if probe.connect_ex(('127.0.0.1',8766))==0:
            known=subprocess.run(['/bin/launchctl','print',f'gui/{os.getuid()}/{LABEL}'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
            if not known:
                raise SystemExit('Port 8766 is already in use. Stop the old manual camera SSH command with Ctrl+C, then run this setup again.')
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    directory.chmod(0o700)
    if not key.exists():
        subprocess.run(['/usr/bin/ssh-keygen','-t','ed25519','-N','','-C','aqvarin-camera-only','-f',str(key)],check=True,stdout=subprocess.DEVNULL)
    key.chmod(0o600)
    code=remote_setup(camera,Path(str(key)+'.pub').read_text())
    print('One-time setup. Enter your Pi login password if requested. Your password is not saved.',flush=True)
    subprocess.run(['/usr/bin/ssh','-t','-o','ConnectTimeout=10',f'{args.user}@{args.host}',
                    '/usr/bin/python3 -c '+shlex.quote(code)],check=True)
    plist.parent.mkdir(parents=True,exist_ok=True)
    plist.write_bytes(plistlib.dumps(agent));plist.chmod(0o600)
    domain=f'gui/{os.getuid()}'
    subprocess.run(['/bin/launchctl','bootout',domain,str(plist)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    subprocess.run(['/bin/launchctl','bootstrap',domain,str(plist)],check=True)
    # No bearer token is needed to verify the local link: 401 proves the camera answers.
    for attempt in range(25):
        try:
            urllib.request.urlopen('http://127.0.0.1:8766/api/camera/health',timeout=2).close()
        except urllib.error.HTTPError as exc:
            if exc.code==401:
                print('Setup complete. Camera link verified. In AQVARIN, use http://127.0.0.1:8766 and your existing camera token, then Connect.\nNext time: hotspot on, power the Pi, open AQVARIN, Connect. No Terminal needed.')
                return
        except OSError: pass
        time.sleep(1)
    raise SystemExit('Autostart installed, but the link is not ready. See '+str(directory/'camera-link-error.log')+'. Keep Mac and Pi on the same network.')


if __name__=='__main__':
    try: main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f'Setup stopped: {exc.cmd[0]} exited {exc.returncode}. No Pi password was saved.') from None
