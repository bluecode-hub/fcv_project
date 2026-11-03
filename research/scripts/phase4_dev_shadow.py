"""Dev test of Component 2 on AID-val: clean image * known soft shadow field (multiplicative illumination, chromaticity
preserved). Truth = clean image. Metrics: PSNR/MAE inside the synthetic shadow, lift of naturally dark *unshadowed*
pixels (darkest 15% of the clean image outside shadow; ideal ~0), PSNR outside the shadow, overall PSNR.
SYNTHETIC: it models shadow as a pure multiplicative factor, which is the assumption TASC relies on. Unit = source image."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd, cv2
REPO = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO))
from research.trs import methods as MT
from research.trs.adapter import run_tasc
from research.v1.registry import v1_methods
from research.v1 import TASCv1, V1Config
from tasc import metrics as M0
from tasc.io_utils import luminance

def shadow_field(h, w, rng):
    m = np.zeros((h, w), np.float32)
    for _ in range(rng.integers(1, 4)):
        c = np.array([rng.uniform(.15, .85) * w, rng.uniform(.15, .85) * h])
        n = rng.integers(5, 9); ang = np.sort(rng.uniform(0, 2 * np.pi, n)); r = rng.uniform(.08, .22) * min(h, w) * rng.uniform(.7, 1.3, n)
        pts = np.stack([c[0] + r * np.cos(ang), c[1] + r * np.sin(ang)], 1).astype(np.int32)
        cv2.fillPoly(m, [pts], 1.0)
    m = cv2.GaussianBlur(m, (0, 0), rng.uniform(1.5, 4.0))     # penumbra
    return np.clip(m, 0, 1)

def main(imgs, out):
    man = json.load(open(REPO / "research/dataset_manifests/aid_subset.json"))
    keys = sorted(k for k, v in man["split"].items() if v == "val")
    cl = MT.classical_methods()
    M = {"Identity": lambda s: s["bands"].copy(), "GlobalGamma": cl["GlobalGamma"],
         "TASC-v0": lambda s: run_tasc(s["bands"], dict(use_dem=False)),
         "TASC-v0/no-global-exposure": lambda s: run_tasc(s["bands"], dict(use_dem=False, global_exposure=False)),
         "CLAHE": cl["CLAHE"]}
    M.update({k: v for k, v in v1_methods(True).items()})
    rows = []
    for k in keys:
        gt = cv2.imread(str(imgs / k)).astype(np.float32) / 255
        if max(gt.shape[:2]) > 600:
            s = 600 / max(gt.shape[:2]); gt = cv2.resize(gt, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        rng = np.random.default_rng(abs(hash(k)) % 2**32 if False else int.from_bytes(k.encode()[:4].ljust(4), "little"))
        sh = shadow_field(*gt.shape[:2], rng); a = rng.uniform(0.55, 0.8)
        x = np.clip(gt * (1 - a * sh)[..., None], 0, 1)
        x = np.clip(np.round((x + rng.normal(0, 0.004, x.shape)) * 255), 0, 255).astype(np.float32) / 255
        Yg, Yx = luminance(gt), luminance(x)
        ins = sh > 0.6; outs = sh < 0.05
        dark_nat = outs & (Yg <= np.percentile(Yg[outs], 15)) if outs.sum() > 100 else None
        for m, f in M.items():
            o = np.clip(f(dict(bands=x)), 0, 1); Yo = luminance(o)
            rows.append(dict(source=k, method=m, shadow_frac=float(ins.mean()),
                             psnr=M0.psnr(o, gt), psnr_shadow=float(10 * np.log10(1 / max(np.mean((Yo[ins] - Yg[ins]) ** 2), 1e-9))) if ins.any() else np.nan,
                             mae_shadow=float(np.abs(Yo - Yg)[ins].mean()) if ins.any() else np.nan,
                             psnr_lit=float(10 * np.log10(1 / max(np.mean((Yo[outs] - Yg[outs]) ** 2), 1e-9))),
                             lift_shadow=float((Yo - Yx)[ins].mean()) if ins.any() else np.nan,
                             lift_natdark=float((Yo - Yx)[dark_nat].mean()) if dark_nat is not None else np.nan,
                             lift_lit=float((Yo - Yx)[outs].mean())))
    d = pd.DataFrame(rows); d.to_csv(out, index=False)
    print(d.groupby("method")[["psnr", "psnr_shadow", "mae_shadow", "psnr_lit", "lift_shadow", "lift_natdark", "lift_lit"]].mean().round(3).to_string())

if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
