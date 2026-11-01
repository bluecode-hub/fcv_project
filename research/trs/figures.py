"""Figures generated from recorded results (tables/*.csv) and a few re-run qualitative panels."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from . import paths

TAB, FIG = paths.RESEARCH / "tables", paths.RESEARCH / "figures"
plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150})
KEY = ["Identity", "HE", "CLAHE", "GlobalGamma", "AGC", "AGCWD", "2D-gamma", "Zero-DCE", "TASC-image", "TASC-DEM"]


def _bar(raw, metrics, title, fname, key=KEY):
    t = pd.read_csv(raw, index_col=0)
    idx = [k for k in key if k in t.index]
    fig, ax = plt.subplots(1, len(metrics), figsize=(2.6 * len(metrics), 2.6), sharey=True)
    ax = np.atleast_1d(ax)
    for a, (m, lab) in zip(ax, metrics.items()):
        if m not in t:
            a.set_visible(False)
            continue
        a.barh(range(len(idx)), t.loc[idx, m], xerr=t.loc[idx, f"{m}_ci"], color=["#c44" if "TASC" in i else "#889" for i in idx], capsize=2)
        a.set_yticks(range(len(idx)), idx)
        a.invert_yaxis()
        a.set_title(lab)
    fig.suptitle(title, fontsize=8, y=1.02)
    fig.tight_layout()
    fig.savefig(FIG / fname, bbox_inches="tight")
    plt.close(fig)


def run(cfg, log):
    FIG.mkdir(exist_ok=True)
    f = TAB / "aid_summary_raw.csv"
    if f.exists():
        _bar(f, {"psnr": "PSNR (dB) ↑", "ssim": "SSIM ↑", "lpips": "LPIPS ↓", "halo": "halo ↓"}, "AID synthetic low light (95% CI over source images)", "fig_aid_methods.png")
    f = TAB / "d2_summary_raw.csv"
    if f.exists():
        _bar(f, {"psnr": "PSNR (dB) ↑", "mae_shadow": "MAE shadow ↓", "lpips": "LPIPS ↓"}, "Landsat D2 (60 pairs)", "fig_d2_methods.png",
             key=["Input", "Identity", "CLAHE", "AGCWD", "Zero-DCE", "TASC-v0", "A4_no_dem", "A3_plus_dem", "TASC-DEM/beta-only",
                  "TASC-DEM/shift4px(720m)", "TASC-DEM/shift16px(2.9km)", "TASC-DEM/flipped-DEM", "TASC-DEM/az+45", "TASC-DEM/el+7"])
    for split in ("dev", "heldout"):
        f = TAB / f"s2_summary_{split}_raw.csv"
        if f.exists():
            _bar(f, {"lift_shadow": "shadow lift ↑", "dark_to_shadow_lift": "dark-lit/shadow lift ↓", "equalisation_gain": "equalisation gain ↑", "bright_clip": "bright clip ↓"},
                 f"Sentinel-2 {split} regions (95% CI over regions)", f"fig_s2_{split}.png",
                 key=["Identity", "CLAHE", "AGCWD", "Zero-DCE", "C-correction", "SCS+C", "TASC-image", "TASC-DEM", "TASC-DEM/beta-only", "TASC-DEM/wrong-DEM",
                      "TASC-DEM/shift300m", "TASC-DEM/shift1km", "TASC-DEM/az+15", "TASC-DEM/az-15", "TASC-DEM/el+7", "TASC-DEM/el-7"])
    log("  figures done")
