"""Component 2 — shadow-vs-dark-material evidence (heuristic confidence in [0, 1], NOT a calibrated probability).

A dark pixel is plausibly an illumination shadow when (a) it is clearly darker than the lit surround, (b) its
log-chromaticity is consistent with the surround it would have if lit (illumination changes intensity far more than
chromaticity; reflectance edges change both — Land & McCann 1971, Finlayson et al. 2006, Tsai 2006) and, with NIR,
(c) it is not water-like (NDWI > 0). Smoothing of the evidence provides spatial continuity: single dark pixels or
objects smaller than the smoothing scale are averaged out. Known failure modes (stated, not hidden): shadows are
bluer than lit ground (skylight), so the chromatic tolerance is deliberately wide; large dark materials surrounded
by brighter ones of the same colour (burn scars, wet soil) are indistinguishable from shadow without a DEM.
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy import ndimage as ndi

EPS = 1e-4
MIN_NORM = 0.01


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def surround_level(Ys: np.ndarray, percentile: float, window_frac: float, work: int = 64) -> np.ndarray:
    """Local lit level: percentile of the smoothed luminance in a large window, computed on a coarse grid
    (memory/time efficient) and bilinearly resampled."""
    H, W = Ys.shape
    f = max(1, int(min(H, W) // work))
    small = cv2.resize(Ys.astype(np.float32), (max(2, W // f), max(2, H // f)), interpolation=cv2.INTER_AREA)
    k = max(3, int(round(window_frac * min(small.shape))) | 1)
    L = ndi.percentile_filter(small, percentile, size=k, mode="nearest")
    L = cv2.GaussianBlur(L, (0, 0), max(1.0, k / 4))
    return cv2.resize(L, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32)


def darkness_evidence(Ys, L, r_hi, r_lo):
    rho = Ys / np.maximum(L, EPS)
    return smoothstep((r_hi - rho) / max(r_hi - r_lo, 1e-6)).astype(np.float32)


def log_chromaticity(bands: np.ndarray, floor: float = 0.005) -> np.ndarray:
    lb = np.log(np.clip(bands, floor, 1.0))
    return lb - lb.mean(-1, keepdims=True)


def material_consistency(bands_s: np.ndarray, D: np.ndarray, sigma_surround: float, tau: float):
    """exp(-(d/tau)^2), d = distance between the pixel's log-chromaticity and that of the lit surround
    (normalised convolution weighted by 1 - D). Returns (M, valid) where valid marks pixels with enough lit support."""
    c = log_chromaticity(bands_s)
    w = (1.0 - D) * (np.linalg.norm(bands_s, axis=-1) >= MIN_NORM)
    w = w.astype(np.float32)
    den = cv2.GaussianBlur(w, (0, 0), sigma_surround)
    num = np.stack([cv2.GaussianBlur(c[..., k] * w, (0, 0), sigma_surround) for k in range(c.shape[-1])], -1)
    sur = num / np.maximum(den, 1e-6)[..., None]
    d = np.linalg.norm(c - sur, axis=-1)
    valid = den > 0.02
    M = np.exp(-(d / tau) ** 2)
    return np.where(valid, M, 0.5).astype(np.float32), valid


def water_likelihood(bands_s: np.ndarray) -> np.ndarray:
    """NDWI-based water likelihood (needs NIR in band 3). 0 where undefined."""
    if bands_s.shape[-1] < 4:
        return np.zeros(bands_s.shape[:2], np.float32)
    g, n = bands_s[..., 1].astype(np.float64), bands_s[..., 3].astype(np.float64)
    s = g + n
    ok = s >= 0.02
    ndwi = np.where(ok, (g - n) / np.where(ok, s, 1.0), -1.0)
    return smoothstep(ndwi / 0.3).astype(np.float32)


def image_confidence(bands: np.ndarray, Y1: np.ndarray, cfg):
    """Returns dict(C, D, M, L, Ys, water): image-only shadow confidence and its parts."""
    H, W = Y1.shape
    s = max(0.8, cfg.sigma_frac * min(H, W))
    Ys = cv2.GaussianBlur(Y1.astype(np.float32), (0, 0), s)
    bs = cv2.GaussianBlur(bands.astype(np.float32), (0, 0), s)
    if bs.ndim == 2:
        bs = bs[..., None]
    L = surround_level(Ys, cfg.ill_percentile, cfg.ill_window_frac)
    D = darkness_evidence(Ys, L, cfg.r_hi, cfg.r_lo)
    M, _ = material_consistency(bs, D, max(4.0, 0.08 * min(H, W)), cfg.chroma_tau)
    wat = water_likelihood(bs)
    C = (D * M * (1.0 - cfg.water_penalty * wat)).astype(np.float32)
    return dict(C=C, D=D, M=M, L=L, Ys=Ys, water=wat)
