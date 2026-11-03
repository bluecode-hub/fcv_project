"""Dev iteration C2b: evidence-gated exposure. Evaluated on dev data only: AID-val clean (G8 |dY|), AID-val degraded (PSNR, C1-style),
Landsat D2-val (PSNR of C2). Grid fixed in advance: (hi,lo) x (t_white, mean_cap)."""
import json, sys, itertools
from pathlib import Path
import numpy as np, pandas as pd, cv2
REPO = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO))
from research.trs.degrade import degrade, MODELS
from research.trs import datasets as DS
from research.v1 import TASCv1, CANDIDATES, variant
from tasc import metrics as M0
from tasc.io_utils import luminance
imgs = Path(sys.argv[1]); out = sys.argv[2]
man = json.load(open(REPO / "research/dataset_manifests/aid_subset.json"))
keys = sorted(k for k, v in man["split"].items() if v == "val")
grid = list(itertools.product([(0.55, 0.35), (0.60, 0.40)], [(0.65, 0.5), (0.75, 0.6)]))
c2 = CANDIDATES["C2_local_image"]
rows = []
gts = []
for k in keys:
    g = cv2.imread(str(imgs / k)).astype(np.float32) / 255
    if max(g.shape[:2]) > 600:
        s = 600 / max(g.shape[:2]); g = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    gts.append((k, g))
d2 = list(DS.d2_samples("val"))
for (hi, lo), (tw, mc) in grid:
    cfg = variant(c2, adequate_hi=hi, adequate_lo=lo, t_white=tw, mean_cap=mc)
    dy, ps, ss = [], [], []
    for k, g in gts:
        dy.append(np.abs(luminance(TASCv1(variant(cfg, local=False))(g)) - luminance(g)).mean())
        for dg in MODELS:
            x = degrade(g, dg, k); o = TASCv1(cfg)(x); ps.append(M0.psnr(o, g)); ss.append(M0.ssim(o, g))
    dp = [M0.psnr(TASCv1(cfg)(s["bands"]), s["gt"]) for s in d2]
    rows.append(dict(hi=hi, lo=lo, t_white=tw, mean_cap=mc, aid_clean_dY=np.mean(dy), aid_deg_psnr=np.mean(ps), aid_deg_ssim=np.mean(ss), d2_val_psnr=np.mean(dp)))
    print(rows[-1], flush=True)
pd.DataFrame(rows).to_csv(out, index=False)
