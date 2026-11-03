import sys, json
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO))
import numpy as np, pandas as pd, cv2, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from research.trs import paths, datasets as DS, experiments as E, s2data
from research.trs.degrade import degrade
FIG = REPO / "research/figures/phase4"; T = REPO / "research/tables/phase4"
rgb = lambda b, g=1.0: np.clip(b[..., [2, 1, 0]] * g, 0, 1)

def summary_chart():
    c = pd.read_csv(T / "comparisons.csv")
    items = [("AID", "aid", "psnr", "dB"), ("iSAID-dark", "isaid", "psnr", "dB"), ("Landsat D2", "d2", "psnr", "dB")]
    fig, ax = plt.subplots(1, 3, figsize=(10, 3.4), sharey=False)
    for a, (nm, ds, m, u) in zip(ax, items):
        rows = []
        for vs, lab in [("TASC-v0", "v0"), ("Identity", "input"), ("GlobalGamma-perband", "per-band\ngamma"), ("Zero-DCE", "Zero-DCE")]:
            r = c[(c.dataset == ds) & (c.ref == "C2_local_image") & (c.metric == m) & (c.vs == vs)]
            if len(r):
                r = r.iloc[0]; rows.append((lab, r["diff"], r.ci_lo, r.ci_hi))
        x = np.arange(len(rows)); d = np.array([r[1] for r in rows]); lo = np.array([r[2] for r in rows]); hi = np.array([r[3] for r in rows])
        a.bar(x, d, color=["#2a7" if v > 0 else "#c44" for v in d]); a.errorbar(x, d, [d - lo, hi - d], fmt="none", ecolor="k", capsize=3)
        a.axhline(0, color="k", lw=.8); a.set_xticks(x); a.set_xticklabels([r[0] for r in rows], fontsize=8); a.set_title(f"{nm} (PSNR, {u})", fontsize=9)
    ax[0].set_ylabel("TASC-v1 (C2) minus comparator"); fig.tight_layout(); fig.savefig(FIG / "fig_delta_psnr.png", dpi=170); plt.close(fig)

def panel(images, titles, path, ncol=None):
    n = len(images); ncol = ncol or n; nrow = int(np.ceil(n / ncol))
    fig, ax = plt.subplots(nrow, ncol, figsize=(2.3 * ncol, 2.4 * nrow))
    for a, im, t in zip(np.atleast_1d(ax).ravel(), images, titles):
        a.imshow(im); a.set_title(t, fontsize=7); a.axis("off")
    for a in np.atleast_1d(ax).ravel()[n:]: a.axis("off")
    fig.tight_layout(); fig.savefig(path, dpi=170); plt.close(fig)

def aid_examples():
    d = pd.read_csv(T / "aid_summary.csv") if False else None
    from research.trs.store import load_rows
    r = load_rows(paths.ROOT / "experiment_outputs/p4_aid/results.jsonl"); r = r[r.status == "ok"]
    p3 = load_rows(paths.ROOT / "experiment_outputs/e_aid/results.jsonl"); p3 = p3[(p3.status == "ok") & p3.method.isin(["GlobalGamma-perband"])]
    t = pd.concat([r[["sample", "method", "psnr"]], p3[["sample", "method", "psnr"]]]).pivot(index="sample", columns="method", values="psnr").dropna(subset=["TASC-v0", "C2_local_image", "GlobalGamma-perband"])
    t = t[t.index.str.endswith("|uniform")]
    picks = {"improves over v0": (t.C2_local_image - t["TASC-v0"]).idxmax(), "fails vs per-band gamma": (t.C2_local_image - t["GlobalGamma-perband"]).idxmin(),
             "median case": (t.C2_local_image - t["TASC-v0"]).sub((t.C2_local_image - t["TASC-v0"]).median()).abs().idxmin()}
    man = json.load(open(REPO / "research/dataset_manifests/aid_subset.json"))
    M = {"TASC-v0": E.p4_rgb_methods("cpu")["TASC-v0"], "TASC-v1 (C2)": E.p4_rgb_methods("cpu")["C2_local_image"], "per-band gamma": E.__dict__["MT"].classical_methods()["GlobalGamma-perband"]}
    ims, tit = [], []
    for lab, key in picks.items():
        k, dg = key.split("|")
        gt = DS.read_bgr(paths.ds("aid") / "images" / k)
        if max(gt.shape[:2]) > 600: s = 600 / max(gt.shape[:2]); gt = cv2.resize(gt, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        x = degrade(gt, dg, k); outs = [x] + [np.clip(f(dict(bands=x)), 0, 1) for f in M.values()] + [gt]
        ims += [rgb(o) for o in outs]; tit += [f"{lab}\ninput ({dg})"] + list(M) + ["reference"]
    panel(ims, tit, FIG / "fig_qual_aid.png", ncol=5)

def d2_example():
    from research.v1 import TASCv1, CANDIDATES, variant
    from tasc.method import TASCGamma
    s = list(DS.d2_samples("test"))[12]
    o = [s["bands"], TASCGamma()(s["bands"], s["dem"], s["dx"], s["sun_az"], s["sun_el"]), TASCv1(variant(CANDIDATES["C2_local_image"]))(s["bands"]),
         TASCv1(variant(CANDIDATES["C3_local_dem"]))(s["bands"], s["dem"], s["dx"], s["sun_az"], s["sun_el"]), s["gt"]]
    panel([rgb(x) for x in o], ["input", "TASC-v0 (DEM)", "TASC-v1 C2", "TASC-v1 C3 (DEM)", "clean reference"], FIG / "fig_qual_d2.png")

def s2_example():
    from research.v1 import TASCv1, CANDIDATES, variant
    from tasc.method import TASCGamma
    from research.trs.adapter import run_tasc
    best = None
    for sc_meta in [m for m in s2data.list_scenes() if m["split"] == "heldout"][:4]:
        sc = s2data.load_scene(sc_meta["name"]); V = s2data.terrain_variants(sc, None)
        for s in s2data.tiles(sc, V):
            f = float((s["S"] > 0.5).mean())
            if s["bands"][..., :3].mean() > 0.25 or f > 0.6:
                continue            # skip snow / fully shadowed tiles (display saturates)
            if best is None or f > best[0]: best = (f, s)
        del sc
    s = best[1]
    o = [s["bands"], run_tasc(s["bands"], {}, S=s["S"]), TASCv1(variant(CANDIDATES["C2_local_image"]))(s["bands"]), TASCv1(variant(CANDIDATES["C3_local_dem"]))(s["bands"], S=s["S"])]
    panel([rgb(x, 2.2) for x in o] + [s["S"]], ["input (x2.2 display)", "TASC-v0 (DEM)", "TASC-v1 C2", "TASC-v1 C3 (DEM)", "DEM shadow proxy S"], FIG / "fig_qual_s2.png")

if __name__ == "__main__":
    summary_chart(); s2_example(); print("ok")
