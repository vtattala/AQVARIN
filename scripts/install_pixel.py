"""Install the prepared test APK and forward the API over an ADB connection."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import ProxyHandler,build_opener

ROOT=Path(__file__).resolve().parent.parent


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--serial',help='Select an authorized device if several are connected')
    parser.add_argument('--connect-only',action='store_true',help='Restore USB API forwarding without reinstalling')
    args=parser.parse_args()
    adb=Path(os.environ.get('ANDROID_HOME',Path(os.environ['LOCALAPPDATA'])/'Android/Sdk'))/'platform-tools/adb.exe'
    if not adb.is_file():raise SystemExit('Android platform-tools are missing. Install them with Android Studio.')
    result=subprocess.run([str(adb),'devices','-l'],capture_output=True,text=True,check=True)
    devices=[line.split() for line in result.stdout.splitlines()[1:] if line.strip()]
    authorized=[d for d in devices if len(d)>1 and d[1]=='device' and not d[0].startswith('emulator-')]
    if args.serial:authorized=[d for d in authorized if d[0]==args.serial]
    if not authorized:
        if any(len(d)>1 and d[1]=='unauthorized' for d in devices):
            raise SystemExit('Unlock your Pixel and accept its Allow USB debugging prompt, then run this again.')
        raise SystemExit('Connect your Pixel 6 using a USB data cable, enable USB debugging, unlock it, and run this again.')
    if len(authorized)!=1:raise SystemExit('Several phones are connected. Run with --serial DEVICE_ID to select the Pixel.')
    device=authorized[0][0]
    prefix=[str(adb),'-s',device]
    model=subprocess.check_output(prefix+['shell','getprop','ro.product.model'],text=True).strip()
    abi=subprocess.check_output(prefix+['shell','getprop','ro.product.cpu.abi'],text=True).strip()
    if not args.serial and model!='Pixel 6':
        raise SystemExit(f'The connected phone is {model}, not Pixel 6. Connect the Pixel, or explicitly select another test phone with --serial.')
    if abi!='arm64-v8a':raise SystemExit(f'The Pixel APK requires arm64-v8a; connected device is {model} ({abi}).')
    print(f'Using {model}',flush=True)
    subprocess.Popen([str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'scripts/start_pelagos.py'),'--service','api'],
                     cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW)
    opener=build_opener(ProxyHandler({}));deadline=time.monotonic()+45
    while True:
        try:
            with opener.open('http://127.0.0.1:8000/api/health',timeout=3) as response:
                if response.status==200:break
        except Exception:pass
        if time.monotonic()>deadline:raise SystemExit('Analysis server did not start. Check outputs/server-logs/api.log.')
        time.sleep(1)
    if not args.connect_only:
        apk=ROOT/'outputs/android/AQVARIN-Pixel6-test.apk'
        if not apk.is_file():raise SystemExit('Build the APK first with Build Android APK.cmd.')
        info=json.loads((apk.parent/'build-info.json').read_text())
        if hashlib.sha256(apk.read_bytes()).hexdigest()!=info['sha256']:
            raise SystemExit('APK does not match its build metadata. Rebuild before installing.')
        if '_adb-tls-' in device:
            # Wireless streaming install was extremely slow on this Pixel.
            # Compress transport, then let Android install the same signed APK.
            remote='/data/local/tmp/aqvarin-test-'+info['sha256'][:12]+'.apk'
            try:
                subprocess.run(prefix+['push','-z','zstd',str(apk),remote],check=True,timeout=150)
                subprocess.run(prefix+['shell','pm','install','-r',remote],check=True,timeout=90)
            finally:
                subprocess.run(prefix+['shell','rm','-f',remote],timeout=15)
        else:
            subprocess.run(prefix+['install','-r',str(apk)],check=True,timeout=150)
    subprocess.run(prefix+['reverse','tcp:8000','tcp:8000'],check=True)
    subprocess.run(prefix+['shell','am','start','-n','com.aegiscoast.mobile/.MainActivity'],check=True)
    print('AQVARIN is open. Server address: http://127.0.0.1:8000. Keep this debugging connection active and this computer running.')
    print('Camera permission is requested when you start Live; choose videos with the Android file picker.')


if __name__=='__main__':main()
