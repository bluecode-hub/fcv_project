"""Component 3 — confidence-weighted DEM guidance.

The DEM gives a *geometric* shadow likelihood S (Horn slope, Lambert, ray-marched cast shadow — established, reused
from the frozen ``tasc.terrain``). Its reliability is uncertain (misregistration, wrong sun metadata, tile
boundaries). TASC-v1 therefore (i) averages S over a small ensemble of sun-angle perturbations (a fraction of
perturbations agreeing = confidence), (ii) searches a small translation to register S to the image and measures the
agreement rho between S and the image-derived darkness D, (iii) turns rho into a trust weight w in [0, 1] (w = 0 for a
wrong DEM), and (iv) lets the DEM raise confidence only where the image is also dark:  C = 1-(1-C_img)(1-w S D).
So DEM evidence can never lift a pixel that the image shows to be lit, and degrades to image-only guidance.
rho0 / rho1 are heuristics fixed on development data, not calibrated probabilities.
"""
from __future__ import annotations

import cv2
import numpy as np

from tasc.terrain import slope_aspect, hillshade, cast_shadow   # frozen, read-only


def shadow_ensemble(dem, dx, sun_az, sun_el, ensemble=((0.0, 0.0),), sigma=2.0, max_steps=400):
    """Mean over sun perturbations of the (unblurred) geometric shadow likelihood, then Gaussian blur."""
    slope, aspect = slope_aspect(dem, dx, dx)
    px = float(np.mean(dx))
    acc = np.zeros(dem.shape, np.float32)
    for da, de in ensemble:
        az, el = (sun_az + da) % 360.0, float(np.clip(sun_el + de, 2.0, 88.0))
        hs = hillshade(slope, aspect, az, el)
        hs = np.where(cast_shadow(dem, px, az, el, max_steps=max_steps), 0.0, hs)
        acc += np.clip(1.0 - hs / np.cos(np.deg2rad(90.0 - el)), 0.0, 1.0)
    S = acc / len(ensemble)
    return cv2.GaussianBlur(S, (0, 0), sigma) if sigma > 0 else S


def _coarse(x, f):
    H, W = x.shape
    return cv2.resize(x.astype(np.float32), (max(2, W // f), max(2, H // f)), interpolation=cv2.INTER_AREA)


def _corr(a, b):
    a = a - a.mean(); b = b - b.mean()
    d = np.sqrt((a * a).mean() * (b * b).mean())
    return float((a * b).mean() / d) if d > 1e-9 else 0.0


def register_and_trust(S: np.ndarray, D: np.ndarray, cfg):
    """Returns (S_registered, trust_weight, info). Agreement is the correlation between S and the image darkness
    evidence D on a coarse grid; the shift search is limited to +-dem_shift_search_px (full-res px)."""
    H, W = S.shape
    f = max(1, int(min(H, W) // 96))
    Sc, Dc = _coarse(S, f), _coarse(D, f)
    r = int(cfg.dem_shift_search_px // f)
    rho0 = _corr(Sc, Dc)
    best, bs = rho0, (0, 0)
    h, w = Sc.shape
    for dy in range(-r, r + 1):
        for dx_ in range(-r, r + 1):
            if (dy, dx_) == (0, 0):
                continue
            a = Sc[max(dy, 0):h + min(dy, 0), max(dx_, 0):w + min(dx_, 0)]
            b = Dc[max(-dy, 0):h + min(-dy, 0), max(-dx_, 0):w + min(-dx_, 0)]
            if a.size < 0.5 * Sc.size:
                continue
            c = _corr(a, b)
            if c > best:
                best, bs = c, (dy, dx_)
    rho, shift = rho0, (0, 0)
    if best - rho0 >= cfg.dem_shift_gain:
        rho, shift = best, (bs[0] * f, bs[1] * f)
        M = np.float32([[1, 0, -shift[1]], [0, 1, -shift[0]]])
        S = cv2.warpAffine(S, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    wgt = float(np.clip((rho - cfg.rho0) / max(cfg.rho1 - cfg.rho0, 1e-6), 0.0, 1.0))
    wgt = wgt * wgt * (3 - 2 * wgt)
    return S, wgt, dict(rho_unshifted=rho0, rho=rho, shift_px=shift, trust=wgt)


def fuse(C_img: np.ndarray, S: np.ndarray, D: np.ndarray, trust: float) -> np.ndarray:
    return (1.0 - (1.0 - C_img) * (1.0 - trust * S * D)).astype(np.float32)
