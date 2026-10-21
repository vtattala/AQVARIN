"""Export a reproducible source snapshot without machine state or private media."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent.parent
DIRECTORIES=('vision','scripts','tests','config','docs','mobile','assets/models','Testing Videos')
ROOT_FILES=('README.md','THIRD_PARTY.md','requirements.txt','requirements-lock.txt','.gitignore',
            '.gitattributes','Start AQVARIN.cmd','Start Pelagos.cmd','Build Android APK.cmd',
            'Install on Pixel 6.cmd','Connect Pixel USB.cmd')
EXCLUDED={'node_modules','__pycache__','.pytest_cache','.expo','dist','build','.gradle','.cxx','expanded','outputs','uploads'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    destination=args.destination.resolve()
    if destination.exists():raise SystemExit('Use a new destination; export never overwrites an existing directory')
    destination.mkdir(parents=True)
    paths=[]
    for directory in DIRECTORIES:
        for current,subdirs,files in os.walk(ROOT/directory):
            subdirs[:]=[d for d in subdirs if d not in EXCLUDED and Path(current,d)!=ROOT/'mobile/android']
            for name in files:
                path=Path(current,name)
                if (not any(p in EXCLUDED for p in path.relative_to(ROOT).parts)
                    and not path.name.endswith(('.local.json','.pyc','.apk','.aab','.jks','.keystore'))
                    and not path.name.startswith('.env')):
                    paths.append(path)
    paths += [ROOT/p for p in ROOT_FILES if (ROOT/p).is_file()]
    paths.append(ROOT/'YOLOv8n Results & Metrics/weights/best.pt')
    manifest={}
    for path in sorted(set(paths)):
        relative=path.relative_to(ROOT)
        target=destination/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,target)
        manifest[relative.as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    (destination/'SOURCE_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(f'Exported {len(manifest)} files to {destination}')


if __name__=='__main__':main()
