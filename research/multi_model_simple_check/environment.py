"""Small documented environment probes; never reads chart answers or calls a model."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
from pathlib import Path

from .settings import BROWSER, BROWSER_LIBS, BROWSER_RUNTIME, PACKAGE


def spec_hash():
    spec = json.loads((PACKAGE / 'env-spec.json').read_text())
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:8]


def witness(allow_shared_gpu=False):
    used, total = map(int, subprocess.check_output(['nvidia-smi','-i','7','--query-gpu=memory.used,memory.total',
        '--format=csv,noheader,nounits'], text=True).strip().split(','))
    assert used < 500 or allow_shared_gpu, 'GPU 7 no longer idle; witness not started'
    assert total - used >= 4096, 'Insufficient free memory for bounded kernel witness'
    import torch
    import torchvision
    import transformers
    import qwen_vl_utils
    import timm
    assert os.environ.get('CUDA_VISIBLE_DEVICES') == '7', 'Only authorized physical GPU 7'
    assert torch.cuda.device_count() == 1
    torch.manual_seed(12345)
    x = torch.randn(32, 32, device='cuda', dtype=torch.float32)
    y = x @ x.T
    torch.cuda.synchronize()
    assert y.shape == (32, 32) and torch.isfinite(y).all()
    print('WITNESS ' + json.dumps(dict(spec_hash=spec_hash(), device=torch.cuda.get_device_name(),
        visible_device=os.environ['CUDA_VISIBLE_DEVICES'], shared_gpu_authorized=allow_shared_gpu,
        preflight_used_mib=used, shape=list(y.shape), sum=float(y.sum()),
        python=__import__('platform').python_version(), packages={p: importlib.metadata.version(p)
        for p in ('torch','torchvision','transformers','accelerate','qwen-vl-utils','timm')})), flush=True)


def prepare_browser():
    """Extract packages into this new app directory, never apt install/update globally."""
    packages = ['libnss3', 'libnspr4', 'libatk1.0-0', 'libatk-bridge2.0-0',
                'libcups2', 'libatspi2.0-0', 'libxdamage1', 'libgbm1', 'libxkbcommon0',
                'libwayland-server0', 'libavahi-common3', 'libavahi-client3', 'libffi7']
    downloads = BROWSER_RUNTIME.parent / 'debs'
    downloads.mkdir(parents=True, exist_ok=True)
    subprocess.run(['apt-get', 'download', *packages], cwd=downloads, check=True)
    versions = []
    for path in sorted(downloads.glob('*.deb')):
        subprocess.run(['dpkg-deb', '-x', str(path), str(BROWSER_RUNTIME)], check=True)
        versions.append(dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            package_info=subprocess.check_output(['dpkg-deb','-f',str(path),'Package','Version'], text=True)))
    (BROWSER_RUNTIME / 'PACKAGE_MANIFEST.json').write_text(json.dumps(versions, indent=2))
    env = {**os.environ, 'LD_LIBRARY_PATH': str(BROWSER_LIBS)}
    result = subprocess.run(['ldd', str(BROWSER)], env=env, text=True, capture_output=True)
    print(result.stdout, flush=True)
    if result.returncode or 'not found' in result.stdout:
        raise RuntimeError('Unresolved browser libraries; no experiment launched')
    subprocess.run([str(BROWSER), '--version'], env=env, check=True)


def browser_witness(timeout_ms=30000):
    from research.decision_evidence_audit import runner
    import time
    with runner.require_playwright()() as pw:
        started = time.monotonic()
        browser = pw.chromium.launch(headless=True, executable_path=str(BROWSER), args=list(runner.BROWSER_LAUNCH_ARGS), timeout=timeout_ms)
        page = browser.new_page()
        page.set_content('<button>Local browser witness</button>')
        assert page.locator('button').inner_text() == 'Local browser witness'
        print('BROWSER_WITNESS ' + browser.version, flush=True)
        print('BROWSER_STARTUP_SECONDS ' + str(time.monotonic() - started), flush=True)
        browser.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--witness', action='store_true')
    p.add_argument('--prepare-browser', action='store_true')
    p.add_argument('--browser-witness', action='store_true')
    p.add_argument('--allow-shared-gpu', action='store_true')
    p.add_argument('--browser-timeout-ms', type=int, choices=(30000,120000), default=30000)
    args = p.parse_args()
    if args.prepare_browser:
        prepare_browser()
    if args.witness:
        witness(args.allow_shared_gpu)
    if args.browser_witness:
        browser_witness(args.browser_timeout_ms)
