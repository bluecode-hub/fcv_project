"""Build the two datasets used in the benchmark.

D1  real tiles  : 256x256 crops of a Landsat 7 (B1 blue, B2 green, B3 red, B4 NIR)
                  composite over the Sierra Nevada, each with the co-registered SRTM DEM
                  and the sun angles estimated from the scene.
D2  synthetic   : flat, well-exposed crops relit with a physically shaped illumination
                  field (DEM hillshade + cast shadow from a mountain tile, cloud-shadow
                  blobs, global under-exposure, Poisson-Gaussian noise, 8-bit
                  quantisation). Ground truth and exact shadow / lit masks are stored.

Usage:
    python scripts/prepare_dataset.py --raw data/raw --out data
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tasc.io_utils import mercator_y_to_lat, luminance, save_rgb, ndwi  # noqa: E402
from tasc.terrain import (estimate_sun_azimuth, sun_elevation_from_overpass,  # noqa: E402
                          illumination)

TILE = 256


def load_scene(raw: Path):
    with rasterio.open(raw / "landsat.tif") as src:
        img = src.read().astype(np.float32)          # (4, H, W) uint8 TOA x 255
        transform, crs, H, W = src.transform, src.crs, src.height, src.width
        res = src.res[0]
    with rasterio.open(raw / "srtm90.tif") as dsrc:
        dem = np.zeros((H, W), np.float32)
        reproject(source=rasterio.band(dsrc, 1), destination=dem,
                  src_transform=dsrc.transform, src_crs=dsrc.crs,
                  dst_transform=transform, dst_crs=crs, resampling=Resampling.bilinear)
    bands = np.moveaxis(img, 0, -1) / 255.0             # ONE common factor -> ratios kept
    valid = (img > 0).all(0) & (dem > -100)
    ys = transform.f + transform.e * (np.arange(H) + 0.5)
    lat = mercator_y_to_lat(ys).astype(np.float32)
    dx = (res * np.cos(np.deg2rad(lat)))[:, None].astype(np.float32)   # ground metres, per row
    return bands.astype(np.float32), dem, valid, dx, lat


def tiles(H, W, size=TILE):
    for r in range(0, H - size + 1, size):
        for c in range(0, W - size + 1, size):
            yield r, c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="data")
    ap.add_argument("--n-synth-per-tile", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    raw, out = Path(a.raw), Path(a.out)
    rng = np.random.default_rng(a.seed)

    bands, dem, valid, dx, lat = load_scene(raw)
    H, W, _ = bands.shape
    print(f"scene {W}x{H}, valid {valid.mean():.3f}, DEM {dem[valid].min():.0f}..{dem[valid].max():.0f} m")

    # Sun angles: the composite has no single acquisition time, so the azimuth is
    # estimated from the image and the elevation from the morning overpass geometry.
    Y = luminance(bands)
    sun_mask = valid & (Y < 0.35) & (ndwi(bands) < 0)          # skip snow and water
    sun = estimate_sun_azimuth(Y, dem, dx, dx, sun_mask)
    sun.update(sun_elevation_from_overpass(sun["sun_az"], float(np.mean(lat))))
    print("estimated sun:", sun)

    illum_scene, slope_scene = illumination(dem, dx, dx, sun["sun_az"], sun["sun_el"])

    # ---------------- D1: real tiles ----------------
    d1 = out / "D1_real"
    (d1 / "preview").mkdir(parents=True, exist_ok=True)
    index, flat_tiles, mountain_tiles = [], [], []
    for r, c in tiles(H, W):
        sl = (slice(r, r + TILE), slice(c, c + TILE))
        v = valid[sl]
        if v.mean() < 0.99:
            continue
        mean_slope = float(np.rad2deg(slope_scene[sl]).mean())
        name = f"r{r:04d}_c{c:04d}"
        meta = dict(name=name, row=r, col=c, mean_slope_deg=mean_slope,
                    mean_lat=float(lat[r:r + TILE].mean()), **sun)
        np.savez_compressed(d1 / f"{name}.npz", bands=bands[sl], dem=dem[sl], dx=dx[r:r + TILE],
                            valid=v, meta=json.dumps(meta))
        save_rgb(d1 / "preview" / f"{name}.jpg", bands[sl], scale=2.5)
        index.append(meta)
        if mean_slope < 4.5:
            flat_tiles.append((r, c))
        if mean_slope > 12.0:
            mountain_tiles.append((r, c))
    (d1 / "index.json").write_text(json.dumps(index, indent=1))
    print(f"D1: {len(index)} tiles ({len(flat_tiles)} flat, {len(mountain_tiles)} mountain)")

    # ---------------- D2: synthetic non-uniform illumination ----------------
    d2 = out / "D2_synth"
    (d2 / "preview").mkdir(parents=True, exist_ok=True)
    yy, xx = np.mgrid[0:TILE, 0:TILE].astype(np.float32)
    index2 = []
    for (r, c) in flat_tiles:
        sl = (slice(r, r + TILE), slice(c, c + TILE))
        src = bands[sl]
        y = luminance(src)
        gt = np.clip(src * (0.80 / np.percentile(y, 99.0)), 0, 1)   # one factor for all bands
        for k in range(a.n_synth_per_tile):
            mr, mc = mountain_tiles[rng.integers(len(mountain_tiles))]
            msl = (slice(mr, mr + TILE), slice(mc, mc + TILE))
            mdem, mdx = dem[msl], dx[mr:mr + TILE]
            s_az, s_el = float(rng.uniform(0, 360)), float(rng.uniform(20, 50))
            illum, _ = illumination(mdem, mdx, mdx, s_az, s_el)
            amb = float(rng.uniform(0.08, 0.20))
            L = amb + (1 - amb) * np.clip(illum, 0, 1.3)                 # terrain part
            cloud = np.ones_like(L)
            n_blobs = int(rng.integers(0, 3))
            for _ in range(n_blobs):
                cy, cx = rng.uniform(0, TILE, 2)
                sig = rng.uniform(20, 50)
                depth = rng.uniform(0.4, 0.7)
                cloud *= 1 - depth * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * sig ** 2))
            exposure = float(rng.uniform(0.35, 0.60))
            Ltot = (L * cloud * exposure).astype(np.float32)
            clean = gt * Ltot[..., None]
            a_shot, s_read = rng.uniform(1e-4, 3e-4), rng.uniform(0.002, 0.005)
            noisy = clean + rng.normal(0, 1, clean.shape) * np.sqrt(a_shot * clean + s_read ** 2)
            deg = np.round(np.clip(noisy, 0, 1) * 255) / 255.0             # 8-bit like the sensor product
            Lrel = L * cloud                                              # illumination without exposure
            gy = luminance(gt)
            masks = dict(
                shadow=Lrel <= 0.40,
                lit=Lrel >= 0.90,
                dark_material=(gy <= np.percentile(gy, 20)) & (Lrel >= 0.90),
                cloud_shadow=cloud <= 0.6,
            )
            name = f"{r:04d}_{c:04d}_v{k}"
            meta = dict(name=name, src=(r, c), dem_src=(int(mr), int(mc)), sun_az=s_az, sun_el=s_el,
                        ambient=amb, exposure=exposure, n_cloud_blobs=n_blobs,
                        split="val" if (len(index2) // a.n_synth_per_tile) % 5 == 0 else "test")
            np.savez_compressed(d2 / f"{name}.npz", bands=deg.astype(np.float32), gt=gt.astype(np.float32),
                                dem=mdem, dx=mdx, illum=Lrel.astype(np.float32), valid=np.ones((TILE, TILE), bool),
                                **{f"mask_{k2}": v2 for k2, v2 in masks.items()}, meta=json.dumps(meta))
            save_rgb(d2 / "preview" / f"{name}_deg.jpg", deg, scale=1.0)
            save_rgb(d2 / "preview" / f"{name}_gt.jpg", gt, scale=1.0)
            index2.append(meta)
    (d2 / "index.json").write_text(json.dumps(index2, indent=1))
    nval = sum(m["split"] == "val" for m in index2)
    print(f"D2: {len(index2)} synthetic pairs ({nval} val / {len(index2) - nval} test)")


if __name__ == "__main__":
    main()
