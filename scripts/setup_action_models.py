"""Reproduce companion assets from the user's repository at a pinned revision."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
folder = ROOT/'assets/models'
manifest = json.loads((folder/'provenance.json').read_text())
for name in ('drowning_yolov8n.pt', 'person_yolov8n.pt'):
    expected = manifest[name]['sha256']
    target = folder/name
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == expected:
        print(name, 'verified')
        continue
    url = f"https://raw.githubusercontent.com/yashpotdar-py/drowning-detection-system/{manifest['revision']}/{manifest[name]['upstream_path']}"
    with urlopen(url, timeout=60) as response:
        contents = response.read()
    if hashlib.sha256(contents).hexdigest() != expected:
        raise ValueError(f'Unexpected checkpoint hash: {name}')
    temporary = target.with_suffix('.download')
    temporary.write_bytes(contents)
    temporary.replace(target)
    print(name, 'downloaded and verified')
