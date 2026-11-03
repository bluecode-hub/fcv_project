"""One documented parameter round for Component 1 on AID-val only (development data).
Grid: t_white x mean_cap (q fixed 95, gamma floor 0.35); metrics RGB PSNR/SSIM and Y-only PSNR; also the
per-image *oracle* global gamma (max Y-PSNR) for diagnosis. Unit = source image."""
import json, sys, itertools
from pathlib import Path
import numpy as np, pandas as pd, cv2
REPO = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO))
from research.trs.degrade import degrade, MODELS
from research.v1 import TASCv1, V1Config
from research.v1.exposure import exposure_gamma
from tasc import metrics as M0
from tasc.io_utils import luminance

imgs = Path(sys.argv[1]); out = sys.argv[2]
man = json.load(open(REPO / "research/dataset_manifests/aid_subset.json"))
keys = sorted(k for k, v in man["split"].items() if v == "val")
grid = list(itertools.product([0.65, 0.75, 0.85], [0.40, 0.50, 0.60]))
rows = []
for k in keys:
    gt = cv2.imread(str(imgs / k)).astype(np.float32) / 255
    if max(gt.shape[:2]) > 600:
        s = 600 / max(gt.shape[:2]); gt = cv2.resize(gt, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    for d in MODELS:
        x = degrade(gt, d, k); Yg = luminance(gt)
        for tw, mc in grid:
            o = TASCv1(V1Config(local=False, use_dem=False, t_white=tw, mean_cap=mc))(x)
            rows.append(dict(source=k, degradation=d, t_white=tw, mean_cap=mc, psnr=M0.psnr(o, gt), ssim=M0.ssim(o, gt),
                             g0=exposure_gamma(luminance(x), 95, tw, mc, 0.35)))
        Y = np.clip(luminance(x), 1e-4, 1)
        best = max(((M0.psnr(np.clip(x * ((Y ** g) / Y)[..., None], 0, 1), gt), g) for g in np.arange(0.3, 1.01, 0.05)))
        rows.append(dict(source=k, degradation=d, t_white=-1, mean_cap=-1, psnr=best[0], ssim=np.nan, g0=best[1]))
pd.DataFrame(rows).to_csv(out, index=False)
d = pd.DataFrame(rows).groupby(["source", "t_white", "mean_cap"])[["psnr", "ssim", "g0"]].mean().reset_index()
print(d.groupby(["t_white", "mean_cap"])[["psnr", "ssim", "g0"]].mean().round(3))
