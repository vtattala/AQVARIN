"""Restore pinned RipScout model assets without changing existing checkpoints."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

folder = Path(__file__).resolve().parent.parent/'assets/models/ripscout'
manifest = json.loads((folder/'provenance.json').read_text())
for name,digest in manifest['files'].items():
    target = folder/name
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
        print(name,'verified')
        continue
    url = f"https://raw.githubusercontent.com/fahimhkhan/ripscout/{manifest['revision']}/FPVDemo/Model/{name}"
    with urlopen(url,timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f'Unexpected RipScout asset hash: {name}')
    temporary = target.with_suffix('.download')
    temporary.write_bytes(data)
    temporary.replace(target)
    print(name,'downloaded and verified')
