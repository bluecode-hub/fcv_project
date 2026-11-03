"""Component 1 — adaptive global exposure.

Fixed-target gamma (TASC-v0: g = ln(0.55)/ln(mean Y)) forces every image to the same mean, which over-exposes
naturally dark scenes and already-adequate images. Here the gamma is anchored on the *bright end* of the image:

    g_hi   = ln(t_white) / ln(q)         q = q-th percentile of Y  (q small -> the whole image is under-exposed)
    g_mean = smallest g in [g_min, 1] with mean(Y**g) <= mean_cap      (bisection; mean(Y**g) is monotone in g)
    g0     = clip(max(g_hi, g_mean), g_min, 1)

Properties (tested): g0 = 1 whenever q >= t_white (no lift for adequately exposed images, including dark scenes that
contain bright objects); g0 is monotone non-decreasing in q; g0 in [g_min, 1]; the result never raises mean(Y) above
mean_cap unless the input mean already exceeds it (then g0 = 1). It is a key/white-point rule in the spirit of
Reinhard et al. (2002) — no novelty is claimed. A single image cannot distinguish "under-exposed" from "dark scene
with no bright objects"; the mean ceiling limits, but does not remove, that ambiguity.
"""
from __future__ import annotations

import numpy as np

EPS = 1e-4


def _subsample(y: np.ndarray, n: int = 200_000) -> np.ndarray:
    f = y.reshape(-1)
    if f.size > n:
        f = f[:: int(np.ceil(f.size / n))]   # deterministic strided subsample
    return f


def exposure_gamma(Y: np.ndarray, q: float = 95.0, t_white: float = 0.75, mean_cap: float = 0.50,
                   g_min: float = 0.35) -> float:
    y = np.clip(_subsample(np.asarray(Y, np.float64)), EPS, 1.0)
    if not np.isfinite(y).all() or y.size == 0:
        return 1.0
    pq = float(np.clip(np.percentile(y, q), 0.02, 0.999))
    g_hi = float(np.log(t_white) / np.log(pq)) if pq < t_white else 1.0
    if y.mean() >= mean_cap:
        return 1.0
    lo, hi = g_min, 1.0
    if np.mean(y ** lo) <= mean_cap:
        g_mean = lo
    else:
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if np.mean(y ** mid) <= mean_cap:
                hi = mid
            else:
                lo = mid
        g_mean = hi
    return float(np.clip(max(g_hi, g_mean), g_min, 1.0))
