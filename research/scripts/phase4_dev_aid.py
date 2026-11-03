"""Stage 2 development run on the AID *validation* split (data allowed for design). Resumable CSV.
usage: python research/scripts/phase4_dev_aid.py --images DIR --out CSV [--lpips] [--zdce] [--tag NAME]"""
import argparse, json, sys, time
from pathlib import Path
import numpy as np, pandas as pd, cv2

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from research.trs import methods as MT, metrics2 as MX          # noqa: E402
from research.trs.degrade import degrade, MODELS                # noqa: E402
from research.trs.adapter import run_tasc                       # noqa: E402
from research.v1.registry import v1_methods                     # noqa: E402


def read_bgr(p):
    return cv2.imread(str(p), cv2.IMREAD_COLOR).astype(np.float32) / 255.0


def methods(zdce):
    M = {"Identity": lambda s: s["bands"].copy(),
         "GlobalGamma": MT.classical_methods()["GlobalGamma"],
         "GlobalGamma-perband": MT.classical_methods()["GlobalGamma-perband"],
         "CLAHE": MT.classical_methods()["CLAHE"],
         "TASC-v0": lambda s: run_tasc(s["bands"], dict(use_dem=False)),
         "TASC-v0/no-global-exposure": lambda s: run_tasc(s["bands"], dict(use_dem=False, global_exposure=False)),
         "TASC-v0/no-DCT": lambda s: run_tasc(s["bands"], dict(use_dem=False, detail=False))}
    M.update(v1_methods(include_ablations=True))
    if zdce:
        M["Zero-DCE"] = MT.ZeroDCETorch()
    return M


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--manifest", default=str(REPO / "research/dataset_manifests/aid_subset.json"))
    ap.add_argument("--lpips", action="store_true"); ap.add_argument("--zdce", action="store_true")
    ap.add_argument("--limit", type=int, default=0); ap.add_argument("--only-v1", action="store_true"); ap.add_argument("--methods", default="")
    a = ap.parse_args()
    man = json.load(open(a.manifest))
    keys = sorted(k for k, v in man["split"].items() if v == "val")
    assert all(man["split"][k] == "val" for k in keys)       # development data only
    if a.limit:
        keys = keys[:a.limit]
    out = Path(a.out)
    done = set()
    rows = []
    if out.exists():
        old = pd.read_csv(out); rows = old.to_dict("records"); done = set(zip(old["sample"], old["method"]))
    M = methods(a.zdce)
    if a.only_v1:
        M = {k: v for k, v in M.items() if k.startswith("C") and not k.startswith("CLAHE")}
    if a.methods:
        M = {k: v for k, v in M.items() if k in a.methods.split(",")}
    t0 = time.time()
    for i, k in enumerate(keys):
        gt = read_bgr(Path(a.images) / k)
        if max(gt.shape[:2]) > 600:
            sc = 600 / max(gt.shape[:2]); gt = cv2.resize(gt, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
        for d in MODELS:
            s = dict(name=f"{k}|{d}", bands=degrade(gt, d, k), gt=gt)
            for m, f in M.items():
                if (s["name"], m) in done:
                    continue
                t = time.perf_counter()
                try:
                    o = np.clip(np.asarray(f(s), np.float32), 0, 1)
                    r = MX.paired(o, s["bands"], gt, with_lpips=a.lpips)
                    from tasc import metrics as M0
                    from tasc.io_utils import luminance
                    Yo, Yg = luminance(o), luminance(gt)
                    r.update(psnr_y=M0.psnr(Yo[..., None].repeat(3, -1), Yg[..., None].repeat(3, -1)),
                             ssim_y=M0.ssim(Yo[..., None].repeat(3, -1), Yg[..., None].repeat(3, -1)), status="ok")
                except Exception as e:
                    r = dict(status=f"fail: {type(e).__name__}: {e}")
                rows.append(dict(sample=s["name"], source=k, degradation=d, method=m, sec=time.perf_counter() - t, **r))
        if (i + 1) % 10 == 0:
            pd.DataFrame(rows).to_csv(out, index=False); print(i + 1, len(keys), f"{time.time()-t0:.0f}s", flush=True)
    pd.DataFrame(rows).to_csv(out, index=False)


if __name__ == "__main__":
    main()
