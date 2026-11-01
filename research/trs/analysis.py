"""Statistics, tables and figures. Everything is computed from the JSONL stores; nothing is typed by hand."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import paths, stats
from .store import load_rows

TAB = paths.RESEARCH / "tables"
FIG = paths.RESEARCH / "figures"

PAIRED = {"psnr": 1, "ssim": 1, "lpips": 0, "mae": 0, "mae_dark_in": 0, "mae_bright": 0, "bright_clip_new": 0,
          "overshoot_bright": 0, "halo": 0, "noise_amp": 0, "blockiness": 0, "ndvi_mae_vs_gt": 0, "sam_vs_gt": 0, "ms_per_mp": 0}
NR = {"entropy": 1, "eme": 1, "avg_grad": 1, "brisque": 0, "niqe": 0, "halo": 0, "noise_amp": 0, "blockiness": 0, "mean_Y": 1,
      "ms_per_mp": 0}
S2M = {**NR, "lift_shadow": 1, "lift_dark_lit": 0, "dark_to_shadow_lift": 0, "lift_bright": 0, "bright_clip": 0,
       "bright_compress": 0, "equalisation_gain": 1, "ndvi_mae": 0, "ndwi_mae": 0, "sam": 0, "band_ratio_dev": 0}
D2M = {"psnr": 1, "ssim": 1, "lpips": 0, "mae_shadow": 0, "mae_lit": 0, "mae_darkmat": 0, "mae_cloud": 0, "overshoot_lit": 0,
       "clip_lit": 0, "ndvi_mae_vs_gt": 0, "sam_vs_gt": 0, "halo": 0, "noise_amp": 0, "blockiness": 0, "ms_per_mp": 0}


def _save(df, name, caption=None, floatfmt=3):
    TAB.mkdir(exist_ok=True)
    df.to_csv(TAB / f"{name}.csv")
    with open(TAB / f"{name}.tex", "w") as f:
        f.write(df.to_latex(float_format=lambda x: f"{x:.{floatfmt}f}", na_rep="--", escape=True,
                            caption=caption, label=f"tab:{name}", position="t"))


def summary_table(df, metrics, unit, pre_unit=None):
    """mean over units with 95 % bootstrap CI half-width, one row per method."""
    rows = {}
    for m in metrics:
        if m not in df:
            continue
        t = stats.unit_table(df, m, unit, pre_unit=pre_unit)
        for meth in t.columns:
            v = t[meth].dropna().values
            lo, hi = stats.boot_ci(v)
            rows.setdefault(meth, {})[m] = v.mean() if len(v) else np.nan
            rows[meth][f"{m}_ci"] = (hi - lo) / 2 if len(v) > 1 else np.nan
            rows[meth]["n_units"] = len(v)
    return pd.DataFrame(rows).T


def compare_all(df, ref, metrics, unit, pre_unit=None, others=None):
    out = []
    for m, hib in metrics.items():
        if m not in df:
            continue
        t = stats.unit_table(df, m, unit, pre_unit=pre_unit)
        cands = [c for c in (others or t.columns) if c != ref]
        c = stats.compare(t, ref, cands, bool(hib))
        if len(c):
            c.insert(0, "metric", m)
            c.insert(0, "ref", ref)
            out.append(c)
    return pd.concat(out) if out else pd.DataFrame()


def fmt_pm(tab, metrics):
    o = pd.DataFrame(index=tab.index)
    for m in metrics:
        if m in tab:
            o[m] = [f"{v:.3f} ± {c:.3f}" if pd.notna(v) and pd.notna(c) else (f"{v:.3f}" if pd.notna(v) else "--")
                    for v, c in zip(tab[m], tab.get(f"{m}_ci", [np.nan] * len(tab)))]
    return o


def run(cfg, log):
    TAB.mkdir(exist_ok=True)
    FIG.mkdir(exist_ok=True)
    R = {}
    od = paths.ROOT / "experiment_outputs"
    # ---------------- Landsat D2 (continuity + GT geometry controls)
    d2 = load_rows(od / "e_landsat_d2/results.jsonl")
    if len(d2):
        d2["unit"] = d2["sample"]
        R["d2_fail"] = int((d2["status"] != "ok").sum())
        s = summary_table(d2, D2M, "unit")
        s.to_csv(TAB / "d2_summary_raw.csv")
        _save(fmt_pm(s, ["psnr", "ssim", "lpips", "mae_shadow", "mae_darkmat", "mae_cloud", "overshoot_lit", "ndvi_mae_vs_gt"]),
              "d2_summary", "Landsat D2 test (60 synthetic pairs): mean $\\pm$ 95\\% bootstrap CI half-width.")
        c = compare_all(d2, "TASC-v0", {k: v for k, v in D2M.items() if k != "ms_per_mp"}, "unit")
        c.to_csv(TAB / "d2_vs_tascv0.csv", index=False)
        R["d2_units"] = int(d2["unit"].nunique())
    # ---------------- AID (E4 / E1 image-only / E6)
    aid = load_rows(od / "e_aid/results.jsonl")
    if len(aid):
        R["aid_fail"] = int((aid["status"] != "ok").sum())
        s = summary_table(aid, PAIRED, "source")
        s.to_csv(TAB / "aid_summary_raw.csv")
        _save(fmt_pm(s, ["psnr", "ssim", "lpips", "mae_dark_in", "mae_bright", "bright_clip_new", "halo", "noise_amp", "ms_per_mp"]),
              "aid_summary", "AID synthetic low light (test split, per-source-image mean over three degradations).")
        c = compare_all(aid, "TASC-image", PAIRED, "source")
        c.to_csv(TAB / "aid_vs_tasc_image.csv", index=False)
        by = aid[aid.status == "ok"].groupby(["degradation", "method"])[["psnr", "ssim", "lpips"]].mean().unstack(0)
        by.to_csv(TAB / "aid_by_degradation.csv")
        R["aid_units"] = int(aid["source"].nunique())
    # ---------------- Sentinel-2 (E2 / E3 / E5 / E6)
    s2 = load_rows(od / "e_sentinel2/results.jsonl")
    if len(s2):
        R["s2_fail"] = int((s2["status"] != "ok").sum())
        for split in ("dev", "heldout", "all"):
            d = s2 if split == "all" else s2[s2["split"] == split]
            if not len(d):
                continue
            # tiles -> scenes -> regions (the independent unit is the region)
            s = summary_table(d, S2M, "region", pre_unit="scene")
            s.to_csv(TAB / f"s2_summary_{split}_raw.csv")
            _save(fmt_pm(s, ["entropy", "avg_grad", "brisque", "niqe", "lift_shadow", "dark_to_shadow_lift", "bright_clip",
                             "equalisation_gain", "ndvi_mae", "sam", "halo", "noise_amp"]),
                  f"s2_summary_{split}", f"Sentinel-2 ({split} regions): mean over regions $\\pm$ 95\\% bootstrap CI half-width.")
            c = compare_all(d, "TASC-DEM", S2M, "region", pre_unit="scene")
            c.to_csv(TAB / f"s2_vs_tasc_dem_{split}.csv", index=False)
        R["s2_regions"] = sorted(s2["region"].dropna().unique().tolist())
        R["s2_scenes"] = int(s2["scene"].nunique())
    # ---------------- unpaired real low light
    for name in ("e_darkrs", "e_exdark"):
        d = load_rows(od / f"{name}/results.jsonl")
        if len(d):
            d["unit"] = d["sample"]
            s = summary_table(d, NR, "unit")
            s.to_csv(TAB / f"{name[2:]}_summary_raw.csv")
            _save(fmt_pm(s, ["entropy", "eme", "avg_grad", "brisque", "niqe", "halo", "noise_amp", "ms_per_mp"]), f"{name[2:]}_summary",
                  f"{name[2:]} (no reference): mean over images $\\pm$ 95\\% bootstrap CI half-width.")
            compare_all(d, "TASC-image", NR, "unit").to_csv(TAB / f"{name[2:]}_vs_tasc_image.csv", index=False)
            R[f"{name[2:]}_units"] = int(d["unit"].nunique())
    # ---------------- iSAID-dark
    d = load_rows(od / "e_isaid_dark/results.jsonl")
    if len(d):
        d["unit"] = d["sample"]
        s = summary_table(d, PAIRED, "unit")
        s.to_csv(TAB / "isaid_summary_raw.csv")
        _save(fmt_pm(s, ["psnr", "ssim", "lpips", "mae_dark_in", "mae_bright", "halo", "noise_amp"]), "isaid_summary",
              "iSAID-dark test.")
        compare_all(d, "TASC-image", PAIRED, "unit").to_csv(TAB / "isaid_vs_tasc_image.csv", index=False)
        R["isaid_units"] = int(d["unit"].nunique())
    # ---------------- downstream
    d = load_rows(od / "e_downstream/results.jsonl")
    if len(d):
        d = d[d["method"] == "acc"]
        t = d.pivot_table(index="variant", columns="degradation", values="acc")
        t.to_csv(TAB / "downstream_accuracy.csv")
        _save(t, "downstream_accuracy", "AID scene classification accuracy with a fixed ResNet-50 + linear head.")
        # paired bootstrap of accuracy difference vs the degraded input (Identity)
        rows = []
        for deg in d["degradation"].unique():
            base = d[(d.degradation == deg) & (d.variant == "Identity")]
            if not len(base):
                continue
            b = pd.Series(json.loads(base.iloc[0]["per_image"]))
            for _, r in d[d.degradation == deg].iterrows():
                v = pd.Series(json.loads(r["per_image"]))
                diff = (v - b).values
                lo, hi = stats.boot_ci(diff)
                rows.append(dict(degradation=deg, variant=r["variant"], acc=r["acc"], diff_vs_identity=diff.mean(), ci_lo=lo, ci_hi=hi))
        pd.DataFrame(rows).to_csv(TAB / "downstream_vs_identity.csv", index=False)
        R["downstream_n"] = int(d["n"].iloc[0])
    # ---------------- efficiency
    ef = od / "e_efficiency/efficiency.json"
    if ef.exists():
        j = json.load(open(ef))
        e = pd.DataFrame(j["rows"]).set_index("method")
        _save(e[["ms_per_mp", "peak_rss_mb"]], "efficiency", "Runtime per megapixel (1 MP image) and peak RSS, CPU only.", 1)
        R["env"] = j["env"]
    json.dump(R, open(paths.RESEARCH / "tables/analysis_summary.json", "w"), indent=1, default=str)
    try:
        from . import figures
        figures.run(cfg, log)
    except Exception as e:
        log(f"  figures failed: {e}")
        R["figures_error"] = str(e)
    return R
