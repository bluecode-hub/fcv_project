"""Terrain utilities: slope, aspect, hillshade and sun-angle estimation.

Conventions
-----------
* DEM is a 2-D float array in metres, rows run north -> south, columns west -> east.
* Pixel size (dx, dy) is the *ground* size in metres. For Web-Mercator (EPSG:3857)
  rasters this is resolution * cos(latitude), which ``ground_pixel_size`` computes.
* Azimuth is measured clockwise from north in degrees (0 = N, 90 = E).
* Sun elevation is in degrees above the horizon; zenith = 90 - elevation.
"""
from __future__ import annotations

import numpy as np
import cv2


def ground_pixel_size(res_m: float, lat_deg: np.ndarray | float) -> np.ndarray | float:
    """Ground pixel size for a Web-Mercator raster at the given latitude(s)."""
    return res_m * np.cos(np.deg2rad(lat_deg))


def slope_aspect(dem: np.ndarray, dx: np.ndarray | float, dy: np.ndarray | float):
    """Slope and aspect (radians) using Horn's 3x3 method.

    ``dx``/``dy`` may be scalars or per-row arrays of shape (H, 1).
    Aspect is the downslope direction, clockwise from north.
    """
    z = np.pad(dem.astype(np.float64), 1, mode="edge")
    a, b, c = z[:-2, :-2], z[:-2, 1:-1], z[:-2, 2:]
    d, f = z[1:-1, :-2], z[1:-1, 2:]
    g, h, i = z[2:, :-2], z[2:, 1:-1], z[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8.0 * dx)   # + towards east
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8.0 * dy)   # + towards south
    slope = np.arctan(np.hypot(dzdx, dzdy))
    # Uphill vector in (east, north) = (dzdx, -dzdy); downslope = (-dzdx, dzdy).
    # Azimuth of a vector (e, n), clockwise from north = atan2(e, n).
    aspect = np.mod(np.arctan2(-dzdx, dzdy), 2 * np.pi)
    return slope.astype(np.float32), aspect.astype(np.float32)


def hillshade(slope: np.ndarray, aspect: np.ndarray, sun_az_deg: float, sun_el_deg: float) -> np.ndarray:
    """Lambertian illumination cos(i) for every pixel, clipped at 0 (self-shadow)."""
    zen = np.deg2rad(90.0 - sun_el_deg)
    az = np.deg2rad(sun_az_deg)
    cos_i = np.cos(zen) * np.cos(slope) + np.sin(zen) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(cos_i, 0.0, None).astype(np.float32)


def cast_shadow(dem: np.ndarray, px: float, sun_az_deg: float, sun_el_deg: float, max_steps: int = 200) -> np.ndarray:
    """Binary cast-shadow mask by marching each pixel towards the sun.

    A pixel is shadowed if any terrain along the ray towards the sun rises above the
    sun line. ``px`` is the (mean) ground pixel size in metres.
    """
    H, W = dem.shape
    az = np.deg2rad(sun_az_deg)
    step_c, step_r = np.sin(az), -np.cos(az)          # towards the sun (east=+col, north=-row)
    tan_el = np.tan(np.deg2rad(sun_el_deg))
    # no ray can be blocked beyond the distance at which the sun line clears the highest peak
    relief = float(np.nanmax(dem) - np.nanmin(dem))
    max_steps = int(min(max_steps, np.ceil(relief / (px * tan_el)) + 1))
    rr, cc = np.mgrid[0:H, 0:W].astype(np.float32)
    shadow = np.zeros((H, W), bool)
    z0 = dem.astype(np.float32)
    for k in range(1, max_steps + 1):
        r = (rr + step_r * k).astype(np.float32)
        c = (cc + step_c * k).astype(np.float32)
        inside = (r >= 0) & (r <= H - 1) & (c >= 0) & (c <= W - 1)
        if not inside.any():
            break
        zk = cv2.remap(z0, c, r, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        sun_line = z0 + k * px * tan_el
        shadow |= inside & (zk > sun_line)
    return shadow


def illumination(dem, dx, dy, sun_az_deg, sun_el_deg, with_cast_shadow=True):
    """Relative illumination: hillshade / cos(zenith), 1 on flat ground, 0 in shadow."""
    slope, aspect = slope_aspect(dem, dx, dy)
    hs = hillshade(slope, aspect, sun_az_deg, sun_el_deg)
    if with_cast_shadow:
        px = float(np.mean(dx))
        hs = np.where(cast_shadow(dem, px, sun_az_deg, sun_el_deg), 0.0, hs)
    flat = np.cos(np.deg2rad(90.0 - sun_el_deg))
    return (hs / flat).astype(np.float32), slope


def _highpass(x: np.ndarray, sigma: float = 12.0) -> np.ndarray:
    x = x.astype(np.float32)
    return x - cv2.GaussianBlur(x, (0, 0), sigma)


def estimate_sun_azimuth(lum: np.ndarray, dem: np.ndarray, dx, dy, mask: np.ndarray,
                         ref_el: float = 45.0, az_step: int = 5, min_slope_deg: float = 8.0):
    """Estimate the sun azimuth from the image when metadata is missing.

    log(L) = log(albedo) + log(cos i). High-passing both sides removes most of the
    slowly varying albedo, so the azimuth whose high-passed log-hillshade correlates
    best with high-passed log-luminance is the sun azimuth. Elevation is NOT
    identifiable this way (correlation rises monotonically as elevation drops), so
    take it from metadata or from ``sun_elevation_from_overpass``.
    """
    slope, aspect = slope_aspect(dem, dx, dy)
    m = mask & (slope > np.deg2rad(min_slope_deg))
    ly = _highpass(np.log(lum + 1e-3))[m]
    ly = (ly - ly.mean()) / (ly.std() + 1e-9)
    scores = []
    for az in range(0, 360, az_step):
        h = _highpass(np.log(hillshade(slope, aspect, az, ref_el) + 0.05))[m]
        h = (h - h.mean()) / (h.std() + 1e-9)
        scores.append((float(np.mean(h * ly)), az))
    corr, az = max(scores)
    return {"sun_az": az, "az_corr": corr}


def sun_elevation_from_overpass(sun_az_deg: float, lat_deg: float, hour_angle_deg: float = -28.0) -> dict:
    """Sun elevation implied by a sun-synchronous morning overpass.

    Landsat 5/7/8/9 and Sentinel-2 cross mid-latitudes at roughly 10:00-10:30 local
    solar time (hour angle about -30 deg to -22 deg). For a fixed hour angle, each
    solar declination gives one (azimuth, elevation) pair; we pick the declination
    whose azimuth matches the image-estimated azimuth and return its elevation.
    """
    phi, H = np.deg2rad(lat_deg), np.deg2rad(hour_angle_deg)
    best = None
    for dec in np.linspace(-23.44, 23.44, 469):
        d = np.deg2rad(dec)
        sin_el = np.sin(phi) * np.sin(d) + np.cos(phi) * np.cos(d) * np.cos(H)
        el = np.arcsin(sin_el)
        cos_az = (np.sin(d) - sin_el * np.sin(phi)) / (np.cos(el) * np.cos(phi))
        az = np.rad2deg(np.arccos(np.clip(cos_az, -1, 1)))      # morning -> az < 180
        err = abs(az - sun_az_deg)
        if best is None or err < best[0]:
            best = (err, float(np.rad2deg(el)), float(dec))
    return {"sun_el": round(best[1], 1), "declination": round(best[2], 2), "az_mismatch": round(best[0], 2)}
