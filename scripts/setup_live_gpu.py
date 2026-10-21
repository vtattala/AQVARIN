"""Install and verify a separate live-only CUDA runtime, preserving upload Python."""
import json
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent.parent


def main():
    runtime = Path(os.environ.get('LOCALAPPDATA',Path.home()))/'Aqvarin/live-runtime'
    if not (runtime/'Scripts/python.exe').is_file():
        venv.EnvBuilder(with_pip=True).create(runtime)
    python = runtime/'Scripts/python.exe'
    # Reuse the already installed non-PyTorch dependencies; local CUDA wheels
    # take precedence over these shared, read-only CPU packages.
    shared = ROOT/'.venv/Lib/site-packages'
    (runtime/'Lib/site-packages/aqvarin-shared.pth').write_text(str(shared)+'\n',encoding='utf-8')
    subprocess.run([str(python),'-X','utf8','-m','pip','install','--no-deps','--ignore-installed',
                    'torch==2.14.0','torchvision==0.29.0','--index-url','https://download.pytorch.org/whl/cu130',
                    '--progress-bar','off'],check=True)
    code = """
import json,sys,sysconfig,torch,torchvision
assert torch.cuda.is_available(), 'CUDA is unavailable in the live runtime'
x=torch.ones((8,8),device='cuda'); assert (x@x).sum().item()==512
print(json.dumps({'python_version':list(sys.version_info[:2]),'site_packages':sysconfig.get_path('purelib'),
 'torch':torch.__version__,'torchvision':torchvision.__version__,'device':torch.cuda.get_device_name(0)}))
"""
    result = subprocess.check_output([str(python),'-X','utf8','-c',code],text=True)
    settings = json.loads(result)
    # Resolve Windows app filesystem redirects so external .cmd launchers can
    # find the same packages after this desktop session ends.
    settings['site_packages'] = str(Path(settings['site_packages']).resolve())
    (ROOT/'config/live-runtime.local.json').write_text(json.dumps(settings,indent=2),encoding='utf-8')
    print('Verified live-only GPU runtime:',settings['device'])
    print('Restart the analysis server when no uploads or live sessions are active.')


if __name__ == '__main__':
    main()
