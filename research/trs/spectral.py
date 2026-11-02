"""Corrected spectral-angle (SAM) evaluation metric.

The frozen ``tasc.metrics.sam_deg`` computes arccos(a.b / (|a||b| + EPS)) in float32 and includes every pixel.
Verified defects (see reports/scientific_corrections.md):
  1. all-zero vectors (reflectance clipped to 0 after the BOA offset) get cos = 0 -> 90 deg even when a == b;
  2. EPS added to the denominator biases cos below 1 by EPS/|a||b|, i.e. an angle of about sqrt(2 EPS)/|a| rad
     for identical vectors (0.8 deg at |a| = 0.1, > 25 deg for |a| < 0.01);
  3. float32 arccos near 1 adds a further resolution error.
This module leaves the frozen code untouched and implements the angle in float64 with the numerically stable
form  angle = 2 asin(|a/|a| - b/|b|| / 2),  no EPS, and an explicit exclusion of invalid / near-zero vectors.
"""
from __future__ import annotations

import numpy as np

MIN_NORM = 0.01          # primary threshold on the L2 norm of a reflectance vector (both vectors must reach it)
MIN_NORM_SENS = 0.03     # sensitivity analysis


def sam_pixels(a, b, min_norm=MIN_NORM):
    """Per-pixel angle in degrees (float64) and a boolean array of pixels that satisfy the norm criterion."""
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    na = np.linalg.norm(a, axis=-1)
    nb = np.linalg.norm(b, axis=-1)
    ok = np.isfinite(na) & np.isfinite(nb) & (na >= min_norm) & (nb >= min_norm)
    ua = a / np.where(ok, na, 1.0)[..., None]
    ub = b / np.where(ok, nb, 1.0)[..., None]
    d = np.linalg.norm(ua - ub, axis=-1)
    ang = np.rad2deg(2.0 * np.arcsin(np.clip(d / 2.0, 0.0, 1.0)))
    return np.where(ok, ang, np.nan), ok


def sam_deg_valid(a, b, valid=None, min_norm=MIN_NORM):
    """Mean angle (deg) over pixels that are inside ``valid`` and have both vector norms >= min_norm.

    Returns dict(sam, n_total, n_valid_mask, n_used, n_excl_invalid, n_excl_norm, frac_used); sam is NaN if no pixel
    qualifies (never silently 0)."""
    ang, ok = sam_pixels(a, b, min_norm)
    inside = np.ones(ok.shape, bool) if valid is None else np.asarray(valid, bool)
    use = inside & ok
    n_in = int(inside.sum())
    n = int(use.sum())
    return dict(sam=float(ang[use].mean()) if n else float("nan"),
                n_total=int(ok.size), n_valid_mask=n_in, n_used=n,
                n_excl_invalid=int(ok.size - n_in), n_excl_norm=int((inside & ~ok).sum()),
                frac_used=n / n_in if n_in else float("nan"))


# ---------------------------------------------------------------------------------------------------------------
# Spectral-index and band-ratio metrics with the same validity handling (correction pass 1, extended)
# The frozen/original versions add 1e-6 / 1e-4 to denominators and include zero-valued (clipped) pixels; a pixel that is
# 0 in the input but lifted by a method then counts as a large NDVI/ratio "error" that is an artefact of clipping.
MIN_SUM = 0.02           # minimum (a + b) of the two bands entering a normalised-difference index (both images)
MIN_BAND = 0.005         # minimum value of every band for the log band-ratio metric (both images)


def _pair_mask(a, b, valid, min_norm):
    na = np.linalg.norm(np.asarray(a, np.float64), axis=-1)
    nb = np.linalg.norm(np.asarray(b, np.float64), axis=-1)
    inside = np.ones(na.shape, bool) if valid is None else np.asarray(valid, bool)
    return inside, inside & (na >= min_norm) & (nb >= min_norm)


def nd_index_mae_valid(a, b, i, j, valid=None, min_norm=MIN_NORM, min_sum=MIN_SUM):
    """Mean |ND(a) - ND(b)| with ND = (x_i - x_j)/(x_i + x_j) (no epsilon) over valid pixels whose two bands sum to
    >= min_sum in both images.  Returns (value, n_used, n_candidate)."""
    a = np.asarray(a, np.float64); b = np.asarray(b, np.float64)
    inside, m = _pair_mask(a, b, valid, min_norm)
    sa, sb = a[..., i] + a[..., j], b[..., i] + b[..., j]
    m &= (sa >= min_sum) & (sb >= min_sum)
    na = (a[..., i] - a[..., j]) / np.where(m, sa, 1.0)
    nb = (b[..., i] - b[..., j]) / np.where(m, sb, 1.0)
    n = int(m.sum())
    return (float(np.abs(na - nb)[m].mean()) if n else float("nan")), n, int(inside.sum())


def band_ratio_dev_valid(a, b, valid=None, min_norm=MIN_NORM, min_band=MIN_BAND):
    """Mean over band pairs of |log(a_i/a_j) - log(b_i/b_j)| (no epsilon) over valid pixels where every band of both
    images is >= min_band.  Identical images and positive common gains give 0 (up to rounding)."""
    a = np.asarray(a, np.float64); b = np.asarray(b, np.float64)
    inside, m = _pair_mask(a, b, valid, min_norm)
    m &= (a.min(-1) >= min_band) & (b.min(-1) >= min_band)
    n = int(m.sum())
    if not n:
        return float("nan"), 0, int(inside.sum())
    la, lb = np.log(np.where(m[..., None], a, 1.0)), np.log(np.where(m[..., None], b, 1.0))
    K = a.shape[-1]
    d = [np.abs((la[..., p] - la[..., q]) - (lb[..., p] - lb[..., q]))[m].mean() for p in range(K) for q in range(p + 1, K)]
    return float(np.mean(d)), n, int(inside.sum())
