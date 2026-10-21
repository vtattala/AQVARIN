"""Build the standalone Pixel test APK locally, without cloud accounts.

Stage outside the apostrophe/OneDrive workspace to keep Gradle/CMake paths short.
The generated Android project and dependencies are copied; source is preserved.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent.parent


def checked(command,**kwargs):
    subprocess.run([str(x) for x in command],check=True,**kwargs)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--architectures',default='arm64-v8a')
    parser.add_argument('--server',default='http://127.0.0.1:8000')
    args=parser.parse_args()
    if not set(args.architectures.split(',')).issubset({'arm64-v8a','x86_64','armeabi-v7a','x86'}):
        raise SystemExit('Unsupported Android architecture')
    sdk=Path(os.environ.get('ANDROID_HOME',Path(os.environ['LOCALAPPDATA'])/'Android/Sdk'))
    java=Path(os.environ.get('JAVA_HOME',r'C:\Program Files\Android\Android Studio\jbr'))
    if not (sdk/'platform-tools/adb.exe').is_file() or not (java/'bin/java.exe').is_file():
        raise SystemExit('Install Android Studio with Android SDK and its Java runtime first.')
    stage=Path(os.environ['USERPROFILE'])/'.aqvarin-build/mobile'
    output=ROOT/'outputs/android'
    output.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,JAVA_HOME=str(java),ANDROID_HOME=str(sdk),ANDROID_SDK_ROOT=str(sdk),
             EXPO_PUBLIC_API_URL=args.server,NODE_ENV='production',CI='1')
    env['PATH']=str(java/'bin')+os.pathsep+env['PATH']
    mobile=ROOT/'mobile'
    node=shutil.which('node.exe')
    if not node: raise SystemExit('Node.js is required')
    checked([node,mobile/'node_modules/expo/bin/cli','prebuild','--platform','android','--no-install'],cwd=mobile,env=env)
    stage.mkdir(parents=True,exist_ok=True)
    print(f'Preparing native build in {stage}',flush=True)
    # No mirror/delete flag: this never removes user source or unrelated files.
    copy=subprocess.run(['robocopy',str(mobile),str(stage),'/E','/COPY:DAT','/DCOPY:T','/R:1','/W:1','/NFL','/NDL','/NJH','/NJS',
                         '/XD',str(mobile/'android/app/build'),str(mobile/'android/build'),
                         str(mobile/'android/.gradle'),str(mobile/'android/app/.cxx'),
                         str(mobile/'.expo'),str(mobile/'dist'),str(mobile/'outputs'),'.cache'],capture_output=True,text=True)
    if copy.returncode >= 8: raise RuntimeError(f'Build staging failed: {copy.stdout[-3000:]} {copy.stderr}')
    (stage/'android/local.properties').write_text('sdk.dir='+sdk.as_posix()+'\n',encoding='utf-8')
    started=time.monotonic()
    log_path=output/'build.log'
    print(f'Building standalone Android APK. Build log: {log_path}',flush=True)
    with log_path.open('w',encoding='utf-8') as log:
        result=subprocess.run(['cmd.exe','/d','/c','gradlew.bat','app:assembleRelease',
            f'-PreactNativeArchitectures={args.architectures}','--no-daemon','--console=plain',
            '--max-workers=2','-Dorg.gradle.jvmargs=-Xmx4096m -XX:MaxMetaspaceSize=1024m'],
            cwd=stage/'android',env=env,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:
        print(log_path.read_text(encoding='utf-8')[-9000:])
        raise SystemExit(f'Android build failed ({result.returncode}); see {log_path}')
    apk=output/'AQVARIN-Pixel6-test.apk'
    shutil.copy2(stage/'android/app/build/outputs/apk/release/app-release.apk',apk)
    manifest={'name':'AQVARIN','package':'com.aegiscoast.mobile','version':'0.1.0','version_code':1,
              'architectures':args.architectures.split(','),'default_api_url':args.server,
              'standalone_js_bundle':True,'signing':'local Android debug key; private testing only',
              'bytes':apk.stat().st_size,'sha256':hashlib.sha256(apk.read_bytes()).hexdigest(),
              'build_seconds':round(time.monotonic()-started,1)}
    (output/'build-info.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    checked([sys.executable,ROOT/'scripts/verify_android.py'],env=env)
    print(f'Ready: {apk} ({apk.stat().st_size/1048576:.1f} MB)',flush=True)


if __name__=='__main__':main()
