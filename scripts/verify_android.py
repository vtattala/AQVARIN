"""Inspect the built APK, including signing, native ABI, bundle and permissions."""
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parent.parent


def main():
    folder=ROOT/'outputs/android'
    apk=folder/'AQVARIN-Pixel6-test.apk'
    if not apk.is_file():raise SystemExit('Build the APK first.')
    sdk=Path(os.environ.get('ANDROID_HOME',Path(os.environ['LOCALAPPDATA'])/'Android/Sdk'))
    versions=sorted((sdk/'build-tools').iterdir(),key=lambda p:tuple(int(v) for v in p.name.split('.') if v.isdigit()),reverse=True)
    tools=next(p for p in versions if (p/'aapt.exe').is_file() and (p/'apksigner.bat').is_file())
    env=dict(os.environ,JAVA_HOME=os.environ.get('JAVA_HOME',r'C:\Program Files\Android\Android Studio\jbr'))
    signing=subprocess.check_output(['cmd.exe','/d','/c',str(tools/'apksigner.bat'),'verify','--verbose',str(apk)],env=env,text=True)
    badging=subprocess.check_output([str(tools/'aapt.exe'),'dump','badging',str(apk)],text=True,encoding='utf-8')
    permissions=subprocess.check_output([str(tools/'aapt.exe'),'dump','permissions',str(apk)],text=True,encoding='utf-8')
    assert "name='com.aegiscoast.mobile'" in badging
    assert "application-label:'AQVARIN'" in badging
    permitted=set(re.findall(r"uses-permission(?:-sdk-23)?: name='([^']+)'",permissions))
    assert {'android.permission.CAMERA','android.permission.INTERNET'} <= permitted
    forbidden={'android.permission.RECORD_AUDIO','android.permission.READ_EXTERNAL_STORAGE','android.permission.WRITE_EXTERNAL_STORAGE',
               'android.permission.READ_MEDIA_IMAGES','android.permission.READ_MEDIA_VIDEO','android.permission.SYSTEM_ALERT_WINDOW'}
    assert not permitted & forbidden,permitted & forbidden
    with zipfile.ZipFile(apk) as package:
        assert 'assets/index.android.bundle' in package.namelist()
        bundle=package.read('assets/index.android.bundle')
        assert len(bundle)>100_000 and b'http://127.0.0.1:8000' in bundle
        abis=sorted({n.split('/')[1] for n in package.namelist() if n.startswith('lib/') and n.endswith('.so')})
        expected=json.loads((folder/'build-info.json').read_text())['architectures']
        assert abis==sorted(expected),abis
        dex=[package.read(n) for n in package.namelist() if re.fullmatch(r'classes\d*\.dex',n)]
        assert any(b'expo/modules/camera/' in data for data in dex)
        assert any(b'expo/modules/aqvarinframecamera/' in data for data in dex)
        assert b'AqvarinFrameCamera' in bundle
    report={'signature_verified':True,'app_label':'AQVARIN','package':'com.aegiscoast.mobile','architectures':abis,
            'embedded_js_bundle':True,'default_server_verified':'http://127.0.0.1:8000','camera_module_packaged':True,
            'continuous_frame_camera_packaged':True,
            'permissions':sorted(permitted),'physical_pixel_test':'not performed by this artifact verifier; see device-verification.json'}
    (folder/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (folder/'apk-badging.txt').write_text(badging,encoding='utf-8')
    (folder/'apk-signature.txt').write_text(signing,encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
