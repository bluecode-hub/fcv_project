"""Synthetic-terrain dev test of Component 3 (AID-val images as albedo; SYNTHETIC DEM and illumination).
Observed = albedo * (k_amb + (1-k_amb) * illum), illum from the frozen tasc.terrain Horn/Lambert/cast-shadow model (so the
'correct DEM' case is circular by construction: it shows the upper bound and the behaviour of the controls, NOT real terrain
accuracy). Controls: shifted DEM, DEM of another image (wrong), sun-azimuth/elevation errors, flipped DEM.
Real-terrain validation (Landsat D2-val, Sentinel-2 dev regions) needs the external drive and is a separate pending gate."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd, cv2
REPO = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO))
from research.v1 import TASCv1, V1Config, CANDIDATES, variant
from research.v1.terrain_guidance import shadow_ensemble
from tasc.terrain import illumination
from tasc import metrics as M0
from tasc.io_utils import luminance

def make_dem(h, w, rng, relief):
    z = np.zeros((h, w), np.float32)
    for s, a in [(80, 1.0), (40, .5), (15, .2)]:
        z += a * cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), s) * s
    z = (z - z.min()) / (z.max() - z.min() + 1e-9)
    return (z ** 1.5 * relief).astype(np.float32)

def main(imgs, out):
    man = json.load(open(REPO / "research/dataset_manifests/aid_subset.json"))
    keys = sorted(k for k, v in man["split"].items() if v == "val")
    c2 = CANDIDATES["C2_local_image"]; c3 = CANDIDATES["C3_local_dem"]
    rows = []
    gts = {}
    for k in keys:
        g = cv2.imread(str(imgs / k)).astype(np.float32) / 255
        if max(g.shape[:2]) > 600:
            s = 600 / max(g.shape[:2]); g = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        gts[k] = g[:512, :512] if min(g.shape[:2]) >= 512 else cv2.resize(g, (512, 512))
    ks = list(gts)
    dx = 10.0
    for i, k in enumerate(ks):
        rng = np.random.default_rng(1000 + i)
        gt = gts[k]; h, w = gt.shape[:2]
        dem = make_dem(h, w, rng, rng.uniform(250, 700))
        az, el = rng.uniform(90, 200), rng.uniform(22, 40)
        ill, _ = illumination(dem, dx, dx, az, el, with_cast_shadow=True)
        k_amb = 0.22
        f = k_amb + (1 - k_amb) * np.clip(ill, 0, 1)
        x = np.clip(np.round(np.clip(gt * f[..., None] + rng.normal(0, 0.004, gt.shape), 0, 1) * 255), 0, 255).astype(np.float32) / 255
        Yg, Yx = luminance(gt), luminance(x)
        sh = f < 0.5; lit = f > 0.95
        nat = lit & (Yg <= np.percentile(Yg[lit], 15)) if lit.sum() > 100 else None
        other = gts[ks[(i + 7) % len(ks)]]
        dem_wrong = make_dem(h, w, np.random.default_rng(5000 + i), 500)
        cases = {"C2 (image only)": ("img", None, None, None),
                 "C3 correct DEM": ("dem", dem, az, el), "C3 shift 8px": ("dem", np.roll(dem, 8, 1), az, el),
                 "C3 shift 24px": ("dem", np.roll(dem, 24, 1), az, el), "C3 wrong DEM": ("dem", dem_wrong, az, el),
                 "C3 flipped DEM": ("dem", dem[::-1].copy(), az, el), "C3 az+15": ("dem", dem, (az + 15) % 360, el),
                 "C3 el+7": ("dem", dem, az, el + 7), "C3 el-7": ("dem", dem, az, el - 7),
                 "C3 correct, no trust": ("dem_nt", dem, az, el), "C3 wrong, no trust": ("dem_nt", dem_wrong, az, el)}
        outs = {"Identity": x}
        for name, (mode, d, a, e) in cases.items():
            if mode == "img":
                outs[name] = TASCv1(variant(c2))(x)
            elif mode == "dem":
                outs[name] = TASCv1(variant(c3))(x, d, dx, a, e)
            else:
                outs[name] = TASCv1(variant(c3, rho0=-2.0, rho1=-1.99))(x, d, dx, a, e)
        for name, o in outs.items():
            Yo = luminance(o)
            rows.append(dict(source=k, case=name, psnr=M0.psnr(o, gt), psnr_shadow=float(10 * np.log10(1 / max(np.mean((Yo[sh] - Yg[sh]) ** 2), 1e-9))) if sh.any() else np.nan,
                             lift_shadow=float((Yo - Yx)[sh].mean()) if sh.any() else np.nan, lift_natdark=float((Yo - Yx)[nat].mean()) if nat is not None else np.nan,
                             lift_lit=float((Yo - Yx)[lit].mean()), shadow_frac=float(sh.mean())))
    d = pd.DataFrame(rows); d.to_csv(out, index=False)
    order = ["Identity"] + list(cases)
    print(d.groupby("case")[["psnr", "psnr_shadow", "lift_shadow", "lift_natdark", "lift_lit", "shadow_frac"]].mean().loc[order].round(3).to_string())

if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
