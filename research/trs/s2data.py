"""Sentinel-2 scene handling: tiles with terrain context for the DEM-aware methods and controls."""
from __future__ import annotations

import json

import numpy as np

from . import paths
from .adapter import shadow_field, crop_blur
from tasc.terrain import slope_aspect, hillshade

TILE = 512


def load_scene(name):
    z = np.load(paths.ds("sentinel2") / f"{name}.npz")
    d = np.load(paths.ds("copernicus_dem") / f"{name}_dem.npz")
    meta = json.loads(str(z["meta"]))
    return dict(bands=z["bands"], scl=z["scl"], valid=z["valid"], dem=d["dem"], meta=meta)


def list_scenes(split=None):
    out = []
    for f in sorted(paths.ds("sentinel2").glob("*.npz")):
        if not (paths.ds("copernicus_dem") / f"{f.stem}_dem.npz").exists():
            continue
        m = json.loads(str(np.load(f)["meta"]))
        if split is None or m["split"] == split:
            out.append(m)
    return out


def terrain_variants(sc, wrong_dem=None):
    """Full-window (DEM grid) shadow fields for the true terrain and every control."""
    m = sc["meta"]
    az, el, dx = m["sun_az"], m["sun_el"], m["dx"]
    dem = sc["dem"]
    V = {"S": shadow_field(dem, dx, az, el, max_steps=400)}
    for px in (30, 100):                                   # DEM translated east by px pixels (300 m / 1 km)
        V[f"shift{px}"] = shadow_field(np.roll(dem, -px, axis=1), dx, az, el, max_steps=400)
    V["az+15"] = shadow_field(dem, dx, (az + 15) % 360, el, max_steps=400)
    V["az-15"] = shadow_field(dem, dx, (az - 15) % 360, el, max_steps=400)
    V["el+7"] = shadow_field(dem, dx, az, min(el + 7, 80), max_steps=400)
    V["el-7"] = shadow_field(dem, dx, az, max(el - 7, 3), max_steps=400)
    if wrong_dem is not None:
        V["wrong"] = shadow_field(wrong_dem, dx, az, el, max_steps=400)
    slope, aspect = slope_aspect(dem, dx, dx)
    V["_cos_i"] = hillshade(slope, aspect, az, el)
    V["_slope"] = slope
    return V


def tiles(sc, V, min_valid=0.95):
    m = sc["meta"]
    M, N = m["dem_margin_px"], m["window_px"]
    for r in range(0, N - TILE + 1, TILE):
        for c in range(0, N - TILE + 1, TILE):
            valid = sc["valid"][r:r + TILE, c:c + TILE]
            if valid.mean() < min_valid:
                continue
            sl = (slice(r + M, r + M + TILE), slice(c + M, c + M + TILE))
            s = dict(name=f"{m['name']}_r{r}c{c}", scene=m["name"], region=m["region"], split=m["split"],
                     bands=sc["bands"][r:r + TILE, c:c + TILE].copy(), scl=sc["scl"][r:r + TILE, c:c + TILE],
                     valid=valid, sun_az=m["sun_az"], sun_el=m["sun_el"], dx=m["dx"])
            for k, S in V.items():
                if k.startswith("_"):
                    continue
                s[k] = crop_blur(S, r + M, c + M, TILE, TILE)
            s["cos_i"], s["slope"] = V["_cos_i"][sl], V["_slope"][sl]
            s["cos_z"] = float(np.cos(np.deg2rad(90 - m["sun_el"])))
            yield s
