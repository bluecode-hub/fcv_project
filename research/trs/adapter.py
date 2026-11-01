"""Adapter around the frozen TASC-v0 implementation (``tasc/`` is never modified).

* RGB samples use the v0 band convention (B, G, R[, NIR]) so v0 code runs unchanged;
  ``luminance`` only reads bands 0-2 and every other v0 step is band-count agnostic.
* ``S_override`` injects a terrain shadow likelihood computed with spatial context
  (large DEM window cropped to the tile), instead of v0's per-tile computation which
  cuts off cast-shadow sources at the tile boundary. Nothing else in v0 is touched.
* Controls (beta-only, wrong DEM, shifted DEM, sun perturbation) are expressed purely as
  alternative S fields / sun angles fed to the same v0 code path.
"""
from __future__ import annotations

import contextlib
import sys

import cv2
import numpy as np

from .paths import REPO

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
import tasc.method as _m  # noqa: E402
from tasc.method import TASCGamma, TASCConfig, ABLATIONS  # noqa: E402,F401
from tasc.terrain import slope_aspect, hillshade, cast_shadow  # noqa: E402


@contextlib.contextmanager
def shadow_override(S):
    """Temporarily make v0's ``shadow_likelihood`` return a precomputed field."""
    orig = _m.shadow_likelihood
    _m.shadow_likelihood = lambda *a, **k: S
    try:
        yield
    finally:
        _m.shadow_likelihood = orig


def shadow_field(dem, dx, sun_az, sun_el, sigma=2.0, max_steps=400):
    """Same maths as v0 ``shadow_likelihood`` (Horn slope, Lambert, ray-marched cast shadow,
    Gaussian sigma) but on an arbitrarily large DEM and with a configurable ray length.
    Returns the *unblurred* S so that it can be cropped before the blur."""
    slope, aspect = slope_aspect(dem, dx, dx)
    hs = hillshade(slope, aspect, sun_az, sun_el)
    hs = np.where(cast_shadow(dem, float(np.mean(dx)), sun_az, sun_el, max_steps=max_steps), 0.0, hs)
    flat = np.cos(np.deg2rad(90.0 - sun_el))
    illum = (hs / flat).astype(np.float32)
    return np.clip(1.0 - illum, 0.0, 1.0)


def crop_blur(S_full, r0, c0, h, w, sigma=2.0):
    S = S_full[r0:r0 + h, c0:c0 + w]
    if sigma > 0:
        S = cv2.GaussianBlur(S, (0, 0), sigma)
    return S.astype(np.float32)


def run_tasc(bands, cfg_overrides=None, *, S=None, dem=None, dx=None, sun_az=None, sun_el=None,
             return_maps=False):
    """Run TASC-Gamma. With ``S`` the terrain prior is injected (DEM-assisted mode);
    without S and without dem the call is image-only. ``bands`` is [H, W, K] BGR(+NIR)."""
    ov = dict(cfg_overrides or {})
    t = TASCGamma(**ov)
    if S is not None:
        with shadow_override(S):
            # dem / sun_az only need to be non-None to enter the terrain branch
            return t(bands, dem=np.zeros(1, np.float32), dx=1.0, sun_az=0.0, sun_el=45.0, return_maps=return_maps)
    return t(bands, dem, dx, sun_az, sun_el, return_maps=return_maps)
