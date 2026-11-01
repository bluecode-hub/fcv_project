"""Select and download Sentinel-2 L2A windows + Copernicus GLO-30 DEM via the public Earth Search STAC API.

Outputs (external drive): datasets/sentinel2/<scene>.npz  (bands B02,B03,B04,B08 as float32 reflectance,
SCL, valid mask, metadata) and datasets/copernicus_dem/<scene>_dem.npz (DEM on the 10 m image grid + margin).
Everything is windowed: only the pixels of the 20 km window are fetched. Idempotent / resumable.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
import yaml
from pyproj import Transformer
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling
from rasterio.windows import Window
from pystac_client import Client

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.trs import paths  # noqa: E402

STAC = "https://earth-search.aws.element84.com/v1"
RES = 10.0
BANDS = [("blue", "B02"), ("green", "B03"), ("red", "B04"), ("nir", "B08")]
GDAL_ENV = dict(AWS_NO_SIGN_REQUEST="YES", AWS_DEFAULT_REGION="us-west-2", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="2", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF", GDAL_HTTP_TIMEOUT="60")


def pick_items(cl, reg, cfg):
    """Ranked candidate list: low sun (long shadows), low cloud, limited snow, one MGRS tile."""
    d = 0.2
    bbox = [reg["lon"] - d, reg["lat"] - d, reg["lon"] + d, reg["lat"] + d]
    res = cl.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=cfg["datetime"],
                    query={"eo:cloud_cover": {"lt": cfg["max_cloud_cover"]}}, max_items=500)
    items = []
    for it in res.items():
        p = it.properties
        el = p.get("view:sun_elevation")
        if el is None or not (cfg["sun_elevation_range"][0] <= el <= cfg["sun_elevation_range"][1]):
            continue
        items.append(it)
    score = lambda i: (i.properties["view:sun_elevation"] + 2 * i.properties["eo:cloud_cover"]
                       + 0.15 * (i.properties.get("s2:snow_ice_percentage") or 0))
    items.sort(key=score)
    return items


def window_in_footprint(item, reg, cfg, epsg):
    """The whole image window must lie inside the item's data footprint (no swath-edge no-data)."""
    from shapely.geometry import shape, box
    from shapely.ops import transform as shp_transform
    import pyproj
    N = cfg["window_px"]
    cx, cy = Transformer.from_crs(4326, epsg, always_xy=True).transform(reg["lon"], reg["lat"])
    half = N * RES / 2 + 200
    poly = box(cx - half, cy - half, cx + half, cy + half)
    f = pyproj.Transformer.from_crs(epsg, 4326, always_xy=True).transform
    return shape(item.geometry).buffer(0).contains(shp_transform(f, poly))


def coarse_check(item, win, N, max_bad=0.01, max_cloud=0.05):
    """Cheap overview read (128x128) of B04 + SCL: reject windows with no-data or cloud before the full download."""
    with rasterio.open(item.assets["red"].href) as ds:
        dn = ds.read(1, window=win, out_shape=(128, 128), resampling=Resampling.nearest)
    nodata = float((dn == 0).mean())
    with rasterio.open(item.assets["scl"].href) as ds:
        sw = Window(win.col_off / 2, win.row_off / 2, N / 2, N / 2)
        scl = ds.read(1, window=sw, out_shape=(128, 128), resampling=Resampling.nearest)
    cloud = float(np.isin(scl, [8, 9, 10, 0]).mean())
    return nodata <= max_bad and cloud <= max_cloud, nodata, cloud


def read_window(href, win, out_shape=None):
    with rasterio.open(href) as ds:
        return ds.read(1, window=win, out_shape=out_shape, resampling=Resampling.nearest if out_shape else Resampling.bilinear), ds


def fetch_scene(item, reg, cfg, cl, dsdir, demdir):
    name = f"{reg['name']}_{item.datetime:%Y%m%d}"
    f_img, f_dem = dsdir / f"{name}.npz", demdir / f"{name}_dem.npz"
    if f_img.exists() and f_dem.exists():
        return name, "cached"
    N, M = cfg["window_px"], cfg["dem_margin_px"]
    epsg = item.properties.get("proj:epsg") or int(str(item.properties["proj:code"]).split(":")[1])
    cx, cy = Transformer.from_crs(4326, epsg, always_xy=True).transform(reg["lon"], reg["lat"])
    # snap the window origin to the 10 m grid of the B02 asset
    with rasterio.open(item.assets["blue"].href) as ref:
        T = ref.transform
        col0 = int(round((cx - T.c) / T.a)) - N // 2
        row0 = int(round((cy - T.f) / T.e)) - N // 2
        H0, W0 = ref.height, ref.width
    if col0 < 0 or row0 < 0 or col0 + N > W0 or row0 + N > H0:
        return name, "reject: window outside tile"
    win = Window(col0, row0, N, N)
    ok, nod, cld = coarse_check(item, win, N)
    if not ok:
        return name, f"reject: coarse check nodata={nod:.3f} cloud/nodata-class={cld:.3f}"
    transform = from_origin(T.c + col0 * T.a, T.f + row0 * T.e, RES, RES)
    bands = np.zeros((N, N, 4), np.float32)
    for k, (an, _) in enumerate(BANDS):
        a = item.assets[an]
        rb = (a.extra_fields.get("raster:bands") or [{}])[0]
        scale, offset = rb.get("scale", 1e-4), rb.get("offset", -0.1)
        with rasterio.open(a.href) as ds:
            dn = ds.read(1, window=win)
        # DN==0 is nodata; reflectance = DN*scale + offset (offset -0.1 for baseline >= 04.00)
        bands[..., k] = np.where(dn > 0, dn.astype(np.float32) * scale + offset, 0.0)
    with rasterio.open(item.assets["scl"].href) as ds:  # 20 m -> 10 m by nearest neighbour
        sw = Window(col0 / 2, row0 / 2, N / 2, N / 2)
        scl = ds.read(1, window=sw, out_shape=(N, N), resampling=Resampling.nearest).astype(np.uint8)
    valid = ~np.isin(scl, [0, 1])          # SCL NO_DATA / saturated-defective (offset can make dark reflectance <= 0)
    bands = np.clip(bands, 0, 1.2)
    # ---- DEM on the image grid + margin (bilinear resampling from 30 m)
    Dn = N + 2 * M
    dtransform = from_origin(transform.c - M * RES, transform.f + M * RES, RES, RES)
    dem = np.full((Dn, Dn), np.nan, np.float32)
    left, bottom = dtransform.c, dtransform.f - Dn * RES
    right, top = dtransform.c + Dn * RES, dtransform.f
    tr = Transformer.from_crs(epsg, 4326, always_xy=True)
    xs, ys = tr.transform([left, right, left, right], [bottom, bottom, top, top])
    dres = cl.search(collections=["cop-dem-glo-30"], bbox=[min(xs), min(ys), max(xs), max(ys)])
    ditems = list(dres.items())
    if not ditems:
        return name, "no DEM coverage"
    for di in ditems:
        with rasterio.open(di.assets["data"].href) as dsrc:
            tmp = np.full((Dn, Dn), np.nan, np.float32)
            reproject(rasterio.band(dsrc, 1), tmp, src_transform=dsrc.transform, src_crs=dsrc.crs,
                      dst_transform=dtransform, dst_crs=f"EPSG:{epsg}", resampling=Resampling.bilinear,
                      src_nodata=dsrc.nodata, dst_nodata=np.nan)
            m = np.isnan(dem) & ~np.isnan(tmp)
            dem[m] = tmp[m]
    cover = float(np.isfinite(dem).mean())
    if cover < 0.99:
        return name, f"DEM coverage only {cover:.2f}"
    dem = np.where(np.isfinite(dem), dem, np.nanmedian(dem))   # sea/nodata -> median (rare)
    p = item.properties
    lat_c = reg["lat"]
    meta = dict(name=name, region=reg["name"], split=reg["split"], item_id=item.id, datetime=p["datetime"],
                sun_az=p["view:sun_azimuth"], sun_el=p["view:sun_elevation"], cloud_cover=p["eo:cloud_cover"],
                epsg=epsg, mgrs=p.get("s2:mgrs_tile"), processing_baseline=p.get("s2:processing_baseline"),
                boa_offset_applied=p.get("earthsearch:boa_offset_applied"), res_m=RES,
                dx=RES, lat=lat_c, lon=reg["lon"], window_px=N, dem_margin_px=M,
                dem_source="Copernicus GLO-30 (cop-dem-glo-30) resampled bilinear to 10 m",
                dem_items=[d.id for d in ditems], transform=list(transform)[:6],
                themes=reg["themes"], scl_valid_frac=float(valid.mean()))
    np.savez_compressed(f_img, bands=bands, scl=scl, valid=valid, meta=json.dumps(meta))
    np.savez_compressed(f_dem, dem=dem.astype(np.float32), meta=json.dumps(meta))
    return name, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(paths.RESEARCH / "protocols/sentinel2_regions.yaml"))
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    paths.check_drive(20)
    cfg = yaml.safe_load(open(a.config))
    dsdir, demdir = paths.ds("sentinel2"), paths.ds("copernicus_dem")
    cl = Client.open(STAC)
    log = []
    with rasterio.Env(**GDAL_ENV):
        for reg in cfg["regions"]:
            if a.only and reg["name"] != a.only:
                continue
            cands = pick_items(cl, reg, cfg)
            accepted, tile = [], None
            for it in cands:
                if len(accepted) >= cfg["acquisitions_per_region"]:
                    break
                epsg = it.properties.get("proj:epsg") or int(str(it.properties["proj:code"]).split(":")[1])
                t = it.properties.get("s2:mgrs_tile") or it.id.split("_")[1]
                d = dt.datetime.fromisoformat(it.properties["datetime"].replace("Z", "+00:00"))
                if tile is not None and t != tile:
                    continue
                if any(abs((d - a_[1]).days) < cfg["min_days_between_acquisitions"] for a_ in accepted):
                    continue
                if not window_in_footprint(it, reg, cfg, epsg):
                    continue
                for attempt in range(3):
                    try:
                        n, st = fetch_scene(it, reg, cfg, cl, dsdir, demdir)
                        break
                    except Exception as e:
                        n, st = it.id, f"error: {type(e).__name__}: {e}"
                print(f"{reg['name']:22s} {n:36s} {st}", flush=True)
                log.append(dict(region=reg["name"], scene=n, status=st, item=it.id))
                if st in ("ok", "cached"):
                    accepted.append((it, d))
                    tile = t
            print(f"{reg['name']}: accepted {len(accepted)}/{cfg['acquisitions_per_region']} (candidates {len(cands)})", flush=True)
    json.dump(log, open(paths.ROOT / "logs/fetch_sentinel2.json", "w"), indent=1)


if __name__ == "__main__":
    main()
