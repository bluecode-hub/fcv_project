"""Parameter round for Component 2 thresholds (r_hi, r_lo) on dev data only: (a) synthetic AID-val shadow test, (b) AID-val degraded
images (to confirm no regression). Criterion fixed beforehand: maximise shadow-region PSNR subject to lit-pixel lift <= 0.015 and
overall PSNR >= identity - 0.5 dB on the shadow test."""
import json, sys, itertools
from pathlib import Path
import numpy as np, pandas as pd, cv2
REPO = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO)); sys.path.insert(0, str(Path(__file__).parent))
from phase4_dev_shadow import shadow_field
from research.v1 import TASCv1, CANDIDATES, variant
from tasc import metrics as M0
from tasc.io_utils import luminance
imgs = Path(sys.argv[1]); out = sys.argv[2]
man = json.load(open(REPO / "research/dataset_manifests/aid_subset.json"))
keys = sorted(k for k, v in man["split"].items() if v == "val")
grid = [(0.80, 0.35), (0.65, 0.30), (0.55, 0.25), (0.50, 0.20)]
rows = []
for k in keys:
    gt = cv2.imread(str(imgs / k)).astype(np.float32) / 255
    if max(gt.shape[:2]) > 600:
        s = 600 / max(gt.shape[:2]); gt = cv2.resize(gt, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    rng = np.random.default_rng(int.from_bytes(k.encode()[:4].ljust(4), "little"))
    sh = shadow_field(*gt.shape[:2], rng); a = rng.uniform(0.55, 0.8)
    x = np.clip(np.round((np.clip(gt * (1 - a * sh)[..., None], 0, 1) + rng.normal(0, 0.004, gt.shape)) * 255), 0, 255).astype(np.float32) / 255
    Yg, Yx = luminance(gt), luminance(x); ins, outs = sh > 0.6, sh < 0.05
    nat = outs & (Yg <= np.percentile(Yg[outs], 15)) if outs.sum() > 100 else None
    for rh, rl in grid:
        o = TASCv1(variant(CANDIDATES["C2_local_image"], r_hi=rh, r_lo=rl, exposure=False))(x); Yo = luminance(o)
        rows.append(dict(source=k, r_hi=rh, r_lo=rl, psnr=M0.psnr(o, gt), psnr_shadow=float(10 * np.log10(1 / max(np.mean((Yo[ins] - Yg[ins]) ** 2), 1e-9))) if ins.any() else np.nan,
                         lift_shadow=float((Yo - Yx)[ins].mean()) if ins.any() else np.nan, lift_lit=float((Yo - Yx)[outs].mean()),
                         lift_natdark=float((Yo - Yx)[nat].mean()) if nat is not None else np.nan))
    rows.append(dict(source=k, r_hi=-1, r_lo=-1, psnr=M0.psnr(x, gt), psnr_shadow=float(10 * np.log10(1 / max(np.mean((Yx[ins] - Yg[ins]) ** 2), 1e-9))) if ins.any() else np.nan, lift_shadow=0, lift_lit=0, lift_natdark=0))
d = pd.DataFrame(rows); d.to_csv(out, index=False)
print(d.groupby(["r_hi", "r_lo"])[["psnr", "psnr_shadow", "lift_shadow", "lift_natdark", "lift_lit"]].mean().round(3))
