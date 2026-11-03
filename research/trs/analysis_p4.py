"""Phase 4 statistics. Merges the Phase 3 stores (baselines, TASC-v0 as 'TASC-image') with the p4_* stores (TASC-v0 recomputed,
TASC-v1 candidates, ablations). Independent units: D2 source crop; Sentinel-2 region; AID source image; iSAID-dark parent image;
DarkRS/ExDark image; classification paired predictions. Holm correction within each dataset x metric family; 95 % bootstrap CI."""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon, binomtest

from . import paths, stats
from .store import load_rows

OUT = paths.RESEARCH / "tables" / "phase4"
V1 = ["C1_exposure", "C2_local_image", "C3_local_dem", "C2b_gated_exposure"]
PAIRED_M = {"psnr": 1, "ssim": 1, "lpips": 0, "mae_dark_in": 0, "bright_clip_new": 0, "halo": 0, "noise_amp": 0}
NR_M = {"entropy": 1, "avg_grad": 1, "niqe": 0, "brisque": 0, "halo": 0, "noise_amp": 0, "mean_Y": 1}
D2_M = {"psnr": 1, "ssim": 1, "lpips": 0, "mae_shadow": 0, "mae_darkmat": 0, "overshoot_lit": 0, "sam_vs_input": 0}
S2_M = {"lift_shadow": 1, "lift_dark_lit": 0, "lift_water": 0, "equalisation_gain": 1, "bright_clip": 0, "niqe": 0, "sam": 0, "ndvi_mae": 0, "band_ratio_dev": 0}
RENAME = {"TASC-image": "TASC-v0", "TASC-image/no-global-exposure": "TASC-v0/no-global-exposure", "TASC-DEM": "TASC-v0-DEM"}


def _rows(name):
    p = paths.ROOT / "experiment_outputs" / name / "results.jsonl"
    d = load_rows(p) if p.exists() else pd.DataFrame()
    return d[d["status"] == "ok"] if len(d) else d


def merged(p3, p4, extra=(), rename=None):
    """Phase 3 rows (renamed v0 names) + Phase 4 rows. Phase 4 wins on duplicate (sample, method). Also returns the
    reproducibility check of recomputed TASC-v0 vs the Phase 3 stored TASC-image rows."""
    a, b = _rows(p3), _rows(p4)
    if len(a):
        a = a.assign(method=a["method"].replace(rename or RENAME))
    chk = {}
    if len(a) and len(b):
        for met in ("psnr", "lift_shadow", "entropy"):
            if met in a and met in b:
                for mname in ("TASC-v0", "TASC-v0-DEM", "Identity"):
                    x = a[a.method == mname].set_index("sample")[met]; y = b[b.method == mname].set_index("sample")[met]
                    j = pd.concat([x, y], axis=1, keys=["p3", "p4"]).dropna()
                    if len(j):
                        chk[f"{mname}:{met}"] = dict(n=len(j), max_abs_diff=float((j.p3 - j.p4).abs().max()))
                break
    for extra_store in extra:
        e = _rows(extra_store)
        if len(e):
            b = pd.concat([b, e.drop(columns=[c for c in e if c in ("status",)], errors="ignore").assign(status="ok")]) if False else b
    d = pd.concat([a, b]).drop_duplicates(["sample", "method"], keep="last") if len(a) or len(b) else pd.DataFrame()
    return d, chk


def add_spectral(d, store_p3, store_p4, cols):
    s = pd.concat([_rows(store_p3).assign(method=lambda x: x.method.replace(RENAME)) if len(_rows(store_p3)) else pd.DataFrame(), _rows(store_p4)])
    if not len(s):
        return d
    s = s[["sample", "method"] + [c for c in cols if c in s]].drop_duplicates(["sample", "method"], keep="last")
    return d.drop(columns=[c for c in cols if c in d], errors="ignore").merge(s, on=["sample", "method"], how="left")


def unit_means(d, metric, unit, pre=None):
    return stats.unit_table(d, metric, unit, pre_unit=pre)


def comparisons(d, metrics, unit, pre, refs, others, dataset):
    rows = []
    for ref in refs:
        for m, hib in metrics.items():
            if m not in d:
                continue
            t = unit_means(d, m, unit, pre)
            c = stats.compare(t, ref, [o for o in others if o != ref], bool(hib))
            if len(c):
                c.insert(0, "metric", m); c.insert(0, "ref", ref); c.insert(0, "dataset", dataset)
                rows.append(c)
    return pd.concat(rows) if rows else pd.DataFrame()


def summary(d, metrics, unit, pre):
    out = {}
    for m in metrics:
        if m not in d:
            continue
        t = unit_means(d, m, unit, pre)
        for meth in t.columns:
            v = t[meth].dropna().values
            lo, hi = stats.boot_ci(v)
            out.setdefault(meth, {})[m] = v.mean() if len(v) else np.nan
            out[meth][m + "_med"] = np.median(v) if len(v) else np.nan
            out[meth][m + "_ci"] = (hi - lo) / 2 if len(v) > 1 else np.nan
            out[meth]["n_units"] = len(v)
    return pd.DataFrame(out).T


def parent(name):
    m = re.search(r"P\d+", name)
    return m.group(0) if m else name


def run(cfg=None, log=print):
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    cmp_all, checks = [], {}

    def go(tag, p3, p4, metrics, unit, pre, prep=None, refs=("TASC-v0", "Identity"), rename=None):
        d, chk = merged(p3, p4, rename=rename)
        if not len(d):
            res[tag] = "no data"; return None
        if prep:
            d = prep(d)
        checks[tag] = chk
        others = sorted(set(d.method))
        best_ref = [r for r in refs if r in set(d.method)]
        res[tag] = dict(rows=len(d), methods=len(others))
        summary(d, metrics, unit, pre).to_csv(OUT / f"{tag}_summary.csv")
        c = comparisons(d, metrics, unit, pre, [m for m in V1 if m in set(d.method)], others, tag)
        if len(c):
            cmp_all.append(c)
        return d

    def aid_prep(d):
        d["source"] = d["sample"].str.split("|").str[0]
        return d

    d = go("aid", "e_aid", "p4_aid", PAIRED_M, "source", "source", aid_prep)
    if d is not None:       # per-degradation view
        d["deg"] = d["sample"].str.split("|").str[1]
        for dg, g in d.groupby("deg"):
            summary(g, PAIRED_M, "source", "source").to_csv(OUT / f"aid_{dg}_summary.csv")
    go("isaid", "e_isaid_dark", "p4_isaid_dark", PAIRED_M, "parent", "sample", lambda d: d.assign(parent=d["sample"].map(parent)))
    go("darkrs", "e_darkrs", "p4_darkrs", NR_M, "sample", None)
    go("exdark", "e_exdark", "p4_exdark", NR_M, "sample", None)

    def d2_prep(d):
        d = add_spectral(d, "e_landsat_d2_spectral", "p4_landsat_d2_spectral", ["sam_vs_input"])
        d["crop"] = d["sample"].str.rsplit("_v", n=1).str[0]
        return d
    go("d2", "e_landsat_d2", "p4_landsat_d2", D2_M, "crop", "sample", d2_prep, rename={"TASC-v0": "TASC-v0-DEM"})

    def s2_prep(d):
        d = add_spectral(d, "e_sentinel2_spectral", "p4_sentinel2_spectral", ["sam", "ndvi_mae", "band_ratio_dev"])
        d["scene"] = d["scene"] if "scene" in d else d["sample"].str.rsplit("_r", n=1).str[0]
        return d
    d = go("s2", "e_sentinel2", "p4_sentinel2", S2_M, "region", "scene", s2_prep)
    if d is not None and "split" in d:
        for sp, g in d.groupby("split"):
            summary(g, S2_M, "region", "scene").to_csv(OUT / f"s2_{sp}_summary.csv")

    # downstream: paired predictions
    a, b = _rows("e_downstream"), _rows("p4_downstream")
    dd = pd.concat([a.assign(variant=a["variant"].replace(RENAME)) if len(a) else a, b]).drop_duplicates(["sample"], keep="last") if (len(a) or len(b)) else pd.DataFrame()
    if len(dd):
        per = {(r.degradation, r.variant): json.loads(r.per_image) for r in dd.itertuples()}
        rows = []
        for deg in sorted({k[0] for k in per}):
            for v in [x for x in V1 + ["TASC-v0"] if (deg, x) in per]:
                for base in [x for x in ("Identity", "TASC-v0", "GlobalGamma-perband", "Zero-DCE") if x != v and (deg, x) in per]:
                    keys = sorted(per[(deg, v)]); x = np.array([per[(deg, v)][k] for k in keys]); y = np.array([per[(deg, base)][k] for k in keys])
                    n01, n10 = int(((x == 1) & (y == 0)).sum()), int(((x == 0) & (y == 1)).sum())
                    p = binomtest(n01, n01 + n10, 0.5).pvalue if n01 + n10 else np.nan
                    lo, hi = stats.boot_ci((x - y).astype(float))
                    rows.append(dict(degradation=deg, variant=v, vs=base, acc=x.mean(), acc_vs=y.mean(), diff=x.mean() - y.mean(), ci_lo=lo, ci_hi=hi, n=len(keys), only_variant_correct=n01, only_other_correct=n10, p_mcnemar_exact=p))
        t = pd.DataFrame(rows)
        if len(t):
            t["p_holm"] = stats.holm(t["p_mcnemar_exact"].values)
        t.to_csv(OUT / "downstream_paired.csv", index=False)
        pd.DataFrame([{"degradation": k[0], "variant": k[1], "acc": float(np.mean(list(v.values())))} for k, v in per.items()]).pivot(index="variant", columns="degradation", values="acc").to_csv(OUT / "downstream_accuracy.csv")
        res["downstream"] = dict(rows=len(t))
    if cmp_all:
        c = pd.concat(cmp_all)
        c["p_holm_family"] = c.groupby(["dataset", "ref", "metric"])["p"].transform(lambda s: pd.Series(stats.holm(s.values), index=s.index))
        c.to_csv(OUT / "comparisons.csv", index=False)
    json.dump(dict(reproducibility_check_v0_vs_phase3=checks, coverage=res), open(OUT / "analysis_status.json", "w"), indent=1, default=str)
    return res


if __name__ == "__main__":
    print(run())
