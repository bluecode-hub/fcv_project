"""Parameter round 2 for Component 1 (AID-val only). Adds the 'adequate image' criterion: on CLEAN val images the exposure
stage must not change the image (mean |dY| <= 0.02). Reports degraded-image PSNR/SSIM (3 degradations) and clean-image |dY|."""
import json, sys, itertools
from pathlib import Path
import numpy as np, pandas as pd, cv2
REPO = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO))
from research.trs.degrade import degrade, MODELS
from research.v1 import TASCv1, V1Config
from tasc import metrics as M0
from tasc.io_utils import luminance
imgs = Path(sys.argv[1]); out = sys.argv[2]
man = json.load(open(REPO / "research/dataset_manifests/aid_subset.json"))
keys = sorted(k for k, v in man["split"].items() if v == "val")
grid = list(itertools.product([0.45, 0.55, 0.65], [0.35, 0.45]))
rows = []
for k in keys:
    gt = cv2.imread(str(imgs / k)).astype(np.float32) / 255
    if max(gt.shape[:2]) > 600:
        s = 600 / max(gt.shape[:2]); gt = cv2.resize(gt, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    for tw, mc in grid:
        t = TASCv1(V1Config(local=False, use_dem=False, t_white=tw, mean_cap=mc))
        o = t(gt)
        rows.append(dict(source=k, degradation="clean", t_white=tw, mean_cap=mc, dY=float(np.abs(luminance(o) - luminance(gt)).mean()),
                         g0=t.info["g0"], psnr=np.nan, ssim=np.nan))
        for d in MODELS:
            x = degrade(gt, d, k); t = TASCv1(V1Config(local=False, use_dem=False, t_white=tw, mean_cap=mc)); o = t(x)
            rows.append(dict(source=k, degradation=d, t_white=tw, mean_cap=mc, dY=np.nan, g0=t.info["g0"], psnr=M0.psnr(o, gt), ssim=M0.ssim(o, gt)))
df = pd.DataFrame(rows); df.to_csv(out, index=False)
a = df[df.degradation == "clean"].groupby(["t_white", "mean_cap"])[["dY", "g0"]].mean()
b = df[df.degradation != "clean"].groupby(["t_white", "mean_cap"])[["psnr", "ssim"]].mean()
print(a.join(b).round(3))
