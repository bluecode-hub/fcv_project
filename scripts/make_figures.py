"""Paper figures from the benchmark outputs.

  fig_qualitative.jpg   input vs baselines vs TASC-Gamma on real and synthetic tiles
  fig_maps.jpg          what the method computes: shadow likelihood, gamma field, gain
  fig_regions.png       shadow lift vs dark-material lift, and NDVI error, per method
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tasc.baselines import build_methods  # noqa: E402
from tasc.io_utils import load_tile, to_rgb8  # noqa: E402
from tasc.method import TASCGamma  # noqa: E402

SHOW = ["Input", "CLAHE", "AGCWD", "Zero-DCE", "GlobalGamma+DCT", "TASC-Gamma"]


def label(img, text):
    img = img.copy()
    cv2.rectangle(img, (0, 0), (img.shape[1], 22), (0, 0, 0), -1)
    cv2.putText(img, text, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def qualitative(methods, out):
    d1 = ROOT / "data/D1_real"
    idx = sorted(json.load(open(d1 / "index.json")), key=lambda m: -m["mean_slope_deg"])
    from tasc.io_utils import ndwi
    water = max(idx, key=lambda m: (ndwi(load_tile(d1 / f"{m['name']}.npz")["bands"]) > 0.1).mean())
    picks = [d1 / f"{idx[0]['name']}.npz", d1 / f"{idx[3]['name']}.npz", d1 / f"{water['name']}.npz"]
    d2 = ROOT / "data/D2_synth"
    tst = [m for m in json.load(open(d2 / "index.json")) if m["split"] == "test"]
    picks += [d2 / f"{tst[0]['name']}.npz", d2 / f"{tst[25]['name']}.npz"]
    rows = []
    for p in picks:
        if not p.exists():
            continue
        t = load_tile(p)
        cells = []
        for name in SHOW:
            o = t["bands"] if name == "Input" else methods[name](t)
            cells.append(label(to_rgb8(o), name))
        if "gt" in t:
            cells.append(label(to_rgb8(t["gt"]), "Ground truth"))
        else:
            cells.append(np.full_like(cells[0], 255))
        rows.append(np.hstack(cells))
    grid = np.vstack(rows)
    cv2.imwrite(str(out / "fig_qualitative.jpg"), cv2.cvtColor(grid, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 92])


def maps(out):
    d1 = ROOT / "data/D1_real"
    idx = sorted(json.load(open(d1 / "index.json")), key=lambda m: -m["mean_slope_deg"])
    t = load_tile(d1 / f"{idx[0]['name']}.npz")
    m = t["meta"]
    o, mp = TASCGamma()(t["bands"], t["dem"], t["dx"], m["sun_az"], m["sun_el"], return_maps=True)
    fig, ax = plt.subplots(1, 5, figsize=(16, 3.6))
    items = [(to_rgb8(t["bands"]), "Input (Landsat 7, true colour)", None),
             (t["dem"], "SRTM DEM (m)", "terrain"),
             (mp["S"], f"Shadow likelihood S (sun {m['sun_az']}°, {m['sun_el']}°)", "magma"),
             (mp["gamma"], "Gamma field γ(x)", "viridis_r"),
             (to_rgb8(o), "TASC-Gamma output", None)]
    for a, (img, title, cmap) in zip(ax, items):
        im = a.imshow(img, cmap=cmap)
        a.set_title(title, fontsize=9)
        a.axis("off")
        if cmap:
            fig.colorbar(im, ax=a, fraction=0.046, pad=0.02)
    fig.tight_layout()
    fig.savefig(out / "fig_maps.jpg", dpi=150)
    plt.close(fig)


def regions(out):
    d1 = pd.read_csv(out / "per_image_D1.csv")
    keep = ["HE", "CLAHE", "AGC", "AGCWD", "2D-gamma", "GlobalGamma+DCT", "Zero-DCE", "A4_no_dem", "TASC-Gamma"]
    g = d1[d1.method.isin(keep)].groupby("method")[["shadow_lift", "darkmat_lift", "ndvi_mae"]].mean().reindex(keep)
    fig, ax = plt.subplots(1, 2, figsize=(12, 4))
    x = np.arange(len(keep))
    ax[0].bar(x - 0.2, g.shadow_lift, 0.4, label="terrain-shadow pixels", color="#4c72b0")
    ax[0].bar(x + 0.2, g.darkmat_lift, 0.4, label="lit dark materials (water, forest)", color="#dd8452")
    ax[0].set_ylabel("mean luminance lift (output − input)")
    ax[0].set_title("D1: who gets brightened?")
    ax[1].bar(x, g.ndvi_mae, color="#55a868")
    ax[1].set_ylabel("NDVI mean absolute error vs input")
    ax[1].set_title("D1: spectral-index distortion")
    for a in ax:
        a.set_xticks(x)
        a.set_xticklabels(keep, rotation=35, ha="right", fontsize=8)
        a.spines[["top", "right"]].set_visible(False)
    ax[0].legend(fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(out / "fig_regions.png", dpi=150)
    plt.close(fig)


def main():
    out = ROOT / "results"
    methods = build_methods(ROOT / "tasc" / "weights", include_ablations=False)
    maps(out)
    regions(out)
    qualitative(methods, out)
    print("figures ->", out)


if __name__ == "__main__":
    main()
