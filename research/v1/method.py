"""TASC-v1 pipeline (all gamma/gain steps on luminance Y; bands touched once, by a shared gain).

  1. adaptive exposure      Y1 = Y ** g0                      (exposure.py)
  2. evidence               C_img from darkness-vs-surround, chromatic consistency, NIR water penalty
  3. optional DEM guidance  C = fuse(C_img, registered S, D, trust)
  4. local lift             target = kappa * surround lit level;  g_loc = clip(ln target / ln Ys, floor, 1)
                            gamma_loc = 1 - C (1 - g_loc), guided-filter smoothed;  Y2 = Y1 ** gamma_loc
  5. (optional DCT detail, OFF by default — see ablations)
  6. shared gain            G = Y_out / Y (capped, soft knee);  B'_k = G B_k  -> band ratios / NDVI / SAM unchanged
Never darkens (gamma <= 1); equal inputs give equal outputs (no randomness).
"""
from __future__ import annotations

import cv2
import numpy as np

from tasc.io_utils import luminance                       # frozen, read-only
from tasc.method import soft_knee_gain, _guided, dct_lowpass   # frozen helpers, imported not modified

from .config import V1Config
from .exposure import exposure_gamma
from . import shadow_confidence as SC
from . import terrain_guidance as TG

EPS = 1e-4


class TASCv1:
    def __init__(self, cfg: V1Config | None = None, **overrides):
        self.cfg = cfg or V1Config()
        for k, v in overrides.items():
            if not hasattr(self.cfg, k):
                raise AttributeError(k)
            setattr(self.cfg, k, v)
        self.info = {}

    def __call__(self, bands, dem=None, dx=None, sun_az=None, sun_el=None, S=None, return_maps=False):
        c = self.cfg
        bands = np.nan_to_num(np.asarray(bands, np.float32), nan=0.0, posinf=1.0, neginf=0.0)
        bands = np.clip(bands, 0.0, 1.0)
        if bands.ndim != 3 or bands.shape[-1] < 3:
            raise ValueError("bands must be [H, W, K>=3] in B, G, R[, NIR] order")
        Y = np.clip(luminance(bands), EPS, 1.0)
        info = {}

        g0 = exposure_gamma(Y, c.exp_q, c.t_white, c.mean_cap, c.gamma_min_global) if c.exposure else 1.0
        Y1 = Y ** g0
        info["g0"] = g0
        gamma = np.full(Y.shape, g0, np.float32)
        Cmap = np.zeros(Y.shape, np.float32)

        if c.local:
            ev = SC.image_confidence(bands, Y1, c)
            C = ev["C"]
            floor = c.gamma_min_local
            have_dem = c.use_dem and (S is not None or (dem is not None and sun_az is not None and sun_el is not None))
            if have_dem:
                if S is None:
                    S = TG.shadow_ensemble(dem, dx, sun_az, sun_el, c.sun_ensemble, c.prior_sigma)
                Sr, trust, tinfo = TG.register_and_trust(np.asarray(S, np.float32), ev["D"], c)
                info.update(tinfo)
                C = TG.fuse(C, Sr, ev["D"], trust)
                floor = c.gamma_min_local - (c.gamma_min_local - c.gamma_min_shadow) * (trust * Sr)
            Ys, L = ev["Ys"], ev["L"]
            target = np.clip(c.target_kappa * L, 0.05, 0.95)
            g_loc = np.clip(np.log(target) / np.log(np.clip(Ys, 1e-3, 0.999)), floor, 1.0)
            gl = 1.0 - C * (1.0 - g_loc)
            gl = np.clip(_guided(Y1, gl.astype(np.float32), c.gf_radius, c.gf_eps), floor, 1.0)
            gl = np.minimum(gl, 1.0)
            gamma = (g0 * gl).astype(np.float32)
            Cmap = C
            Y2 = Y ** gamma
        else:
            Y2 = Y1

        if c.detail:
            base = dct_lowpass(Y2, c.dct_cutoff)
            lit = cv2.GaussianBlur(Y, (0, 0), 4.0)
            k = 1.0 + (c.k_max - 1.0) * np.clip(lit / 0.55, 0.0, 1.0) ** 0.5
            Y2 = np.clip(Y2 + (k - 1.0) * (Y2 - base), 0.0, 1.0)

        if not c.shared_gain:
            out = np.clip(np.clip(bands, EPS, 1.0) ** gamma[..., None], 0, 1)
        else:
            G = np.minimum(np.maximum(Y2, 0) / Y, c.gain_cap)
            G = soft_knee_gain(G, bands, c.knee, c.top)
            out = np.clip(bands * G[..., None], 0, 1)
        out = out.astype(np.float32)
        self.info = info
        if return_maps:
            return out, dict(gamma=gamma, C=Cmap, info=info)
        return out
