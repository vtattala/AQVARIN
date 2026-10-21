"""Optional CUDA packages loaded only inside the isolated live worker."""
import json
import sys
from pathlib import Path

from .config import ROOT

CONFIG = ROOT / 'config/live-runtime.local.json'


def activate_live_runtime(config=CONFIG):
    if not config.is_file():
        return
    settings = json.loads(config.read_text(encoding='utf-8'))
    if settings['python_version'] != list(sys.version_info[:2]):
        raise RuntimeError('Live GPU runtime uses a different Python version; rerun scripts/setup_live_gpu.py')
    site = Path(settings['site_packages'])
    if not (site/'torch/__init__.py').is_file():
        raise RuntimeError('Live GPU runtime is missing; rerun scripts/setup_live_gpu.py')
    if 'torch' in sys.modules:
        raise RuntimeError('Live runtime must be selected before loading PyTorch')
    # This function runs in the spawned camera process, never in the API or
    # upload process. The original CPU environment and upload weights stay intact.
    sys.path.insert(0,str(site))

