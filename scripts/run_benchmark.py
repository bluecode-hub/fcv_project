"""Run every method on D1 (real tiles), D2 (synthetic test split) and the full scene.

Outputs (in --out, default results/):
  per_image_D1.csv, per_image_D2.csv, full_scene.csv  raw numbers
  summary_D1.csv, summary_D2.csv                       mean +- std per method
  wilcoxon.csv                                         paired tests vs TASC-Gamma
  outputs/                                             enhanced full-scene previews

Usage:
  python scripts/run_benchmark.py                 # everything
  python scripts/run_benchmark.py --skip-scene    # tiles only (faster)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tasc.baselines import build_methods  # noqa: E402
from tasc.io_utils import load_tile, save_rgb  # noqa: E402
from tasc.method import shadow_likelihood  # noqa: E402
from tasc.metrics import metrics_real, metrics_synth, real_masks  # noqa: E402

D2_MASKS = ["shadow", "lit", "dark_material", "cloud_shadow"]


def run_d2(methods, data: Path):
    idx = [m for m in json.load(open(data / "index.json")) if m["split"] == "test"]
    rows = []
    for m in idx:
        t = load_tile(data / f"{m['name']}.npz")
        masks = {k: t[f"mask_{k}"] for k in D2_MASKS}
        rows.append(dict(method="Input", image=m["name"], **metrics_synth(t["bands"], t["bands"], t["gt"], masks)))
        for name, f in methods.items():
            t0 = time.perf_counter()
            out = f(t)
            dt = time.perf_counter() - t0
            r = metrics_synth(out, t["bands"], t["gt"], masks)
            rows.append(dict(method=name, image=m["name"], ms_per_mp=dt * 1e3 / (out.shape[0] * out.shape[1] / 1e6), **r))
    return pd.DataFrame(rows)


def run_d1(methods, data: Path):
    idx = json.load(open(data / "index.json"))
    rows = []
    for m in idx:
        t = load_tile(data / f"{m['name']}.npz")
        S = shadow_likelihood(t["dem"], t["dx"], m["sun_az"], m["sun_el"], cast=True, sigma=0)
        masks = real_masks(t["bands"], S)
        base = dict(image=m["name"], mean_slope=m["mean_slope_deg"])
        rows.append(dict(method="Input", **base, **metrics_real(t["bands"], t["bands"], masks)))
        for name, f in methods.items():
            t0 = time.perf_counter()
            out = f(t)
            dt = time.perf_counter() - t0
            r = metrics_real(out, t["bands"], masks)
            rows.append(dict(method=name, **base, ms_per_mp=dt * 1e3 / (out.shape[0] * out.shape[1] / 1e6), **r))
    return pd.DataFrame(rows)


def run_scene(methods, raw: Path, out_dir: Path):
    from scripts.prepare_dataset import load_scene
    from tasc.terrain import estimate_sun_azimuth, sun_elevation_from_overpass
    from tasc.io_utils import luminance, ndwi
    bands, dem, valid, dx, lat = load_scene(raw)
    Y = luminance(bands)
    sun = estimate_sun_azimuth(Y, dem, dx, dx, valid & (Y < 0.35) & (ndwi(bands) < 0))
    sun.update(sun_elevation_from_overpass(sun["sun_az"], float(lat.mean())))
    t = dict(bands=bands, dem=dem, dx=dx, meta=sun)
    S = shadow_likelihood(dem, dx, sun["sun_az"], sun["sun_el"], cast=True, sigma=0)
    masks = {k: v & valid for k, v in real_masks(bands, S).items()}
    out_dir.mkdir(parents=True, exist_ok=True)
    save_rgb(out_dir / "scene_Input.jpg", bands)
    rows = [dict(method="Input", **metrics_real(bands, bands, masks, nr=("niqe", "brisque")))]
    for name, f in methods.items():
        if name.startswith("A") and name[1].isdigit():
            continue                              # ablations: tiles only
        t0 = time.perf_counter()
        out = f(t)
        dt = time.perf_counter() - t0
        out[~valid] = 0
        r = metrics_real(out, bands, masks, nr=("niqe", "brisque"))
        rows.append(dict(method=name, ms_per_mp=dt * 1e3 / (bands.shape[0] * bands.shape[1] / 1e6), **r))
        save_rgb(out_dir / f"scene_{name}.jpg", out)
        print(f"  scene {name}: {dt:.1f}s")
    return pd.DataFrame(rows)


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    num = df.drop(columns=[c for c in ["image", "mean_slope"] if c in df]).groupby("method")
    mean, std = num.mean(numeric_only=True), num.std(numeric_only=True)
    out = mean.copy()
    for c in mean.columns:
        out[c] = [f"{m:.4g} ± {s:.2g}" if not np.isnan(m) else "–" for m, s in zip(mean[c], std[c])]
    return out


def paired_tests(df: pd.DataFrame, dataset: str, metrics: dict, ref="TASC-Gamma"):
    rows = []
    piv = {k: df.pivot(index="image", columns="method", values=k) for k in metrics}
    for k, better in metrics.items():
        for other in piv[k].columns:
            if other in (ref, "Input"):
                continue
            a, b = piv[k][ref], piv[k][other]
            ok = a.notna() & b.notna()
            if ok.sum() < 6 or np.allclose(a[ok], b[ok]):
                continue
            p = wilcoxon(a[ok], b[ok]).pvalue
            wins = ((a[ok] < b[ok]) if better == "lower" else (a[ok] > b[ok])).mean()
            rows.append(dict(dataset=dataset, metric=k, vs=other, better=better, n=int(ok.sum()),
                             tasc_mean=a[ok].mean(), other_mean=b[ok].mean(), tasc_win_rate=wins, p_value=p))
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--out", default=str(ROOT / "results"))
    ap.add_argument("--skip-scene", action="store_true")
    a = ap.parse_args()
    data, out = Path(a.data), Path(a.out)
    out.mkdir(exist_ok=True)
    methods = build_methods(ROOT / "tasc" / "weights")
    print("methods:", list(methods))

    d2 = run_d2(methods, data / "D2_synth")
    d2.to_csv(out / "per_image_D2.csv", index=False)
    summarise(d2).to_csv(out / "summary_D2.csv")
    print("D2 done")

    d1 = run_d1(methods, data / "D1_real")
    d1.to_csv(out / "per_image_D1.csv", index=False)
    summarise(d1).to_csv(out / "summary_D1.csv")
    print("D1 done")

    tests = pd.concat([
        paired_tests(d2, "D2", {"psnr": "higher", "ssim": "higher", "mae_shadow": "lower", "mae_darkmat": "lower",
                                "overshoot_lit": "lower", "ndvi_mae_vs_gt": "lower"}),
        paired_tests(d1, "D1", {"shadow_entropy": "higher", "darkmat_to_shadow": "lower", "bright_clip": "lower",
                                "ndvi_mae": "lower", "brisque": "lower"}),
    ])
    tests.to_csv(out / "wilcoxon.csv", index=False)

    if not a.skip_scene:
        sc = run_scene(methods, data / "raw", out / "outputs")
        sc.to_csv(out / "full_scene.csv", index=False)
    print("done ->", out)


if __name__ == "__main__":
    main()
