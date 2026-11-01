"""E8: runtime per megapixel and peak RSS, each method in a fresh process (so ru_maxrss is per-method)."""
from __future__ import annotations

import json
import platform
import resource
import subprocess
import sys
import time

import numpy as np

from . import paths


def child(method, img_path):
    import cv2
    from . import experiments as E
    im = cv2.imread(img_path).astype(np.float32) / 255.0
    im = cv2.resize(im, (1024, 1024), interpolation=cv2.INTER_AREA)
    M = E.rgb_methods("cpu")
    f = M[method]
    s = dict(bands=im)
    base = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    f(s)                                      # warm-up
    ts = []
    for _ in range(3):
        t = time.perf_counter(); f(s); ts.append(time.perf_counter() - t)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps(dict(method=method, ms_per_mp=1e3 * min(ts) / (im.shape[0] * im.shape[1] / 1e6),
                          peak_rss_mb=peak / 1024, rss_before_mb=base / 1024)))


def run(cfg, log):
    from . import experiments as E
    import cv2, glob
    img = sorted(glob.glob(str(paths.ds("darkrs") / "extracted" / "**" / "*.jp*g"), recursive=True))
    if not img:
        return dict(status="skipped: no DarkRS image")
    out = paths.out_dir("e_efficiency")
    rows = []
    for m in E.rgb_methods("cpu"):
        r = subprocess.run([sys.executable, "-m", "research.trs.efficiency", m, img[0]], capture_output=True, text=True,
                           cwd=str(paths.REPO), env={"OMP_NUM_THREADS": "4", "PATH": "/usr/bin:/bin", "HOME": "/tmp"})
        try:
            rows.append(json.loads(r.stdout.strip().splitlines()[-1]))
            log(f"  {m}: {rows[-1]['ms_per_mp']:.0f} ms/MP, {rows[-1]['peak_rss_mb']:.0f} MB")
        except Exception:
            rows.append(dict(method=m, status="fail", err=r.stderr[-200:]))
    import torch
    env = dict(platform=platform.platform(), python=sys.version.split()[0], cpu=platform.processor(),
               cores=__import__("os").cpu_count(), torch=torch.__version__, cv2=cv2.__version__,
               numpy=np.__version__, gpu_used=False, note="all methods run single process, 4 OpenMP threads, CPU only")
    json.dump(dict(env=env, rows=rows), open(out / "efficiency.json", "w"), indent=1)
    return dict(status="ok", n=len(rows))


if __name__ == "__main__":
    child(sys.argv[1], sys.argv[2])
