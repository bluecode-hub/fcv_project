"""Baseline enhancement methods (re-implementations).

Each single-channel function maps a float image in [0, 1] to [0, 1].
``apply_per_band`` runs it on every band independently (the usual practice for
multispectral data); ``apply_shared_gain`` runs it on luminance and applies the
resulting gain to all bands (the TASC-Gamma C3 trick, used for the fairness check).

Notes on fidelity: HE and CLAHE use OpenCV. AGC (Rahman 2016), AGCWD (Huang 2013)
and 2-D gamma (Lee et al. style, illumination from a guided filter) follow the
published formulas. "Global gamma + DCT" is a Kansal & Tripathi (2019)-style
re-implementation (global adaptive gamma followed by a DCT high-frequency boost),
not the authors' code. Zero-DCE uses the authors' pretrained weights.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import cv2

from .io_utils import luminance
from .method import TASCGamma, ABLATIONS, _guided, soft_knee_gain
from .zerodce import ZeroDCE

EPS = 1e-4


def _u8(x):
    return np.clip(np.round(x * 255), 0, 255).astype(np.uint8)


def he(ch):
    return cv2.equalizeHist(_u8(ch)).astype(np.float32) / 255.0


def clahe(ch, clip=2.0, tiles=8):
    return cv2.createCLAHE(clip, (tiles, tiles)).apply(_u8(ch)).astype(np.float32) / 255.0


def agc_rahman(ch, tau=3.0):
    I = np.clip(ch, 0, 1).astype(np.float64)
    mu, sigma = I.mean(), I.std()
    if 4 * sigma <= 1.0 / tau:                      # low contrast
        g = -np.log2(max(sigma, 1e-4))
    else:
        g = np.exp((1.0 - (mu + sigma)) / 2.0)
    Ig = I ** g
    if mu < 0.5:                                    # dark image
        Ig = Ig / (Ig + (1.0 - Ig) * mu ** g)
    return np.clip(Ig, 0, 1).astype(np.float32)


def agcwd(ch, alpha=0.5):
    x = _u8(ch)
    pdf = np.bincount(x.ravel(), minlength=256).astype(np.float64) / x.size
    pmin, pmax = pdf.min(), pdf.max()
    pdf_w = pmax * ((pdf - pmin) / (pmax - pmin + 1e-12)) ** alpha
    cdf_w = np.cumsum(pdf_w) / pdf_w.sum()
    lut = 255.0 * (np.arange(256) / 255.0) ** (1.0 - cdf_w)
    return lut[x].astype(np.float32) / 255.0


def gamma2d(ch, radius=16, eps=1e-2):
    I = np.clip(ch, EPS, 1).astype(np.float32)
    illum = _guided(I, cv2.GaussianBlur(I, (0, 0), radius / 2), radius, eps)
    m = float(illum.mean())
    g = np.power(0.5, (m - illum) / max(m, EPS))
    return np.clip(I ** g, 0, 1).astype(np.float32)


SINGLE_CHANNEL = {"HE": he, "CLAHE": clahe, "AGC": agc_rahman, "AGCWD": agcwd, "2D-gamma": gamma2d}


def apply_per_band(fn, bands):
    return np.stack([fn(bands[..., k]) for k in range(bands.shape[-1])], -1)


def apply_shared_gain(fn, bands):
    Y = np.clip(luminance(bands), EPS, 1)
    G = soft_knee_gain(fn(Y) / Y, bands)
    return np.clip(bands * G[..., None], 0, 1)


class ZeroDCEBaseline:
    """Zero-DCE on the RGB bands; NIR gets the mean RGB gain (the model only knows RGB)."""

    def __init__(self, weights):
        self.net = ZeroDCE(weights)

    def __call__(self, bands):
        rgb = bands[..., [2, 1, 0]]
        out_rgb = self.net.enhance_rgb(rgb)
        gain = out_rgb.mean(-1) / np.maximum(rgb.mean(-1), EPS)
        out = bands.copy()
        out[..., [2, 1, 0]] = out_rgb
        out[..., 3] = np.clip(bands[..., 3] * gain, 0, 1)
        return out


def build_methods(weights_dir: str | Path | None = None, include_ablations=True):
    """Returns {name: callable(tile_dict) -> bands}."""
    M = {}
    for name, fn in SINGLE_CHANNEL.items():
        M[name] = (lambda f: (lambda t: apply_per_band(f, t["bands"])))(fn)
    a0 = TASCGamma(**ABLATIONS["A0_global_gamma_dct"], shared_gain=False)
    M["GlobalGamma+DCT"] = lambda t: a0(t["bands"])
    if weights_dir is not None:
        w = Path(weights_dir) / "zerodce_Epoch99.pth"
        if w.exists():
            z = ZeroDCEBaseline(w)
            M["Zero-DCE"] = lambda t: z(t["bands"])
    full = TASCGamma()
    M["TASC-Gamma"] = lambda t: full(t["bands"], t.get("dem"), t.get("dx"),
                                      t["meta"]["sun_az"], t["meta"]["sun_el"])
    if include_ablations:
        for name, ov in ABLATIONS.items():
            if name == "A4_full":
                continue
            f = TASCGamma(**ov)
            M[name] = (lambda f: (lambda t: f(t["bands"], t.get("dem"), t.get("dx"),
                                               t["meta"]["sun_az"], t["meta"]["sun_el"])))(f)
        # fairness check for RQ3: strongest classical baselines with the shared-gain trick
        M["AGCWD+shared"] = lambda t: apply_shared_gain(agcwd, t["bands"])
        M["CLAHE+shared"] = lambda t: apply_shared_gain(clahe, t["bands"])
    return M
