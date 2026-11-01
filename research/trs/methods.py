"""Method registry for all experiments.

Every method is ``f(sample) -> float32 array [H, W, K]`` in the v0 band order (B, G, R[, NIR]).
A sample is a dict with ``bands`` and optionally ``S`` (terrain prior), ``dem_tile``, ``dx``,
``sun_az``, ``sun_el``, ``S_wrong``, ``S_shift`` (dict of shift->S), ``S_sun`` (dict of key->S).

Provenance of each baseline is recorded in PROVENANCE and written into the reports.
"""
from __future__ import annotations

import numpy as np
import cv2

from .adapter import run_tasc, ABLATIONS
from .paths import REPO
import tasc.baselines as B  # v0 re-implementations (HE, CLAHE, AGC, AGCWD, 2D-gamma)
from tasc.io_utils import luminance
from tasc.method import soft_knee_gain, _gamma_from_mean

EPS = 1e-4
ZDCE_W = REPO / "tasc" / "weights" / "zerodce_Epoch99.pth"

PROVENANCE = {
    "Identity": "no processing",
    "HE": "OpenCV equalizeHist per band (standard)",
    "CLAHE": "OpenCV CLAHE per band, clip 2.0, 8x8 tiles (standard)",
    "GlobalGamma": "independent: Y**g, g=ln(tau)/ln(mean Y), shared gain (tau=0.55)",
    "GlobalGamma-perband": "independent: same global gamma applied to each band",
    "AGC": "independent re-implementation of Rahman et al. 2016 (v0 code)",
    "AGCWD": "independent re-implementation of Huang et al. 2013 (v0 code)",
    "AGCWD+shared": "AGCWD curve applied through the shared-gain transform",
    "CLAHE+shared": "CLAHE applied through the shared-gain transform",
    "2D-gamma": "independent Lee-style guided-filter illumination gamma (v0 code); NOT the published SAGC",
    "C-correction": "independent implementation of Teillet et al. 1982 (needs DEM + sun)",
    "SCS+C": "independent implementation of Soenen et al. 2005 (needs DEM + sun)",
    "Zero-DCE": "official released weights (Epoch99.pth), PyTorch re-implementation of the network, verified against the v0 NumPy port",
    "TASC-image": "frozen TASC-v0, image-only mode",
    "TASC-DEM": "frozen TASC-v0 with DEM prior (context-aware shadow field via adapter)",
}


# ------------------------------------------------------------------ helpers
def _shared(fn, bands):
    Y = np.clip(luminance(bands), EPS, 1)
    G = soft_knee_gain(fn(Y) / Y, bands)
    return np.clip(bands * G[..., None], 0, 1).astype(np.float32)


def global_gamma_fn(tau=0.55, gmin=0.4):
    def f(y):
        g = float(_gamma_from_mean(y.mean(), tau, gmin))
        return np.clip(y, EPS, 1) ** g
    return f


def terrain_correction(bands, dem_cos_i, cos_z, slope, mode):
    """Topographic correction per band. ``dem_cos_i`` = cos(incidence angle)."""
    out = np.empty_like(bands)
    ci = dem_cos_i.reshape(-1)
    ok = (bands.max(-1) > 0).reshape(-1)
    for k in range(bands.shape[-1]):
        rho = bands[..., k].reshape(-1)
        A = np.vstack([ci[ok], np.ones(ok.sum())]).T
        m, b = np.linalg.lstsq(A, rho[ok], rcond=None)[0]
        c = b / m if abs(m) > 1e-6 else 1e3
        if mode == "C":
            f = (cos_z + c) / (dem_cos_i + c)
        else:  # SCS+C
            f = (np.cos(slope) * cos_z + c) / (dem_cos_i + c)
        f = np.clip(np.where(np.isfinite(f), f, 1.0), 0.2, 5.0)
        out[..., k] = np.clip(bands[..., k] * f, 0, 1)
    return out


class ZeroDCETorch:
    """Zero-DCE with the authors' weights in PyTorch (exactly the network used by tasc.zerodce)."""
    def __init__(self, weights=ZDCE_W, device="cpu"):
        import torch
        from tasc.zerodce import load_legacy_state_dict
        self.torch = torch
        p = load_legacy_state_dict(weights)
        self.p = {k: torch.from_numpy(v).to(device) for k, v in p.items()}
        self.dev = device

    def rgb(self, rgb):
        t = self.torch
        F = t.nn.functional
        x = t.from_numpy(np.ascontiguousarray(rgb.transpose(2, 0, 1)))[None].float().to(self.dev)
        c = lambda i, z: F.conv2d(z, self.p[f"e_conv{i}.weight"], self.p[f"e_conv{i}.bias"], padding=1)
        with t.no_grad():
            x1 = F.relu(c(1, x)); x2 = F.relu(c(2, x1)); x3 = F.relu(c(3, x2)); x4 = F.relu(c(4, x3))
            x5 = F.relu(c(5, t.cat([x3, x4], 1))); x6 = F.relu(c(6, t.cat([x2, x5], 1)))
            r = t.tanh(c(7, t.cat([x1, x6], 1)))
            y = x
            for k in range(8):
                y = y + r[:, 3 * k:3 * k + 3] * (y * y - y)
        return y.clamp(0, 1)[0].permute(1, 2, 0).cpu().numpy()

    def __call__(self, bands):
        out = bands.copy()
        out[..., :3] = self.rgb(bands[..., [2, 1, 0]])[..., ::-1]
        if bands.shape[-1] > 3:  # NIR gets the mean RGB gain, as in v0
            rgb = bands[..., [2, 1, 0]]
            g = out[..., :3].mean(-1) / np.maximum(rgb.mean(-1), EPS)
            out[..., 3] = np.clip(bands[..., 3] * g, 0, 1)
        return out


# ------------------------------------------------------------------ TASC variants
def _tasc(overrides, use_S="S"):
    def f(s):
        S = s.get(use_S) if use_S else None
        return run_tasc(s["bands"], overrides, S=S)
    return f


def _tasc_S_const(overrides, value):
    def f(s):
        S = np.full(s["bands"].shape[:2], value, np.float32)
        return run_tasc(s["bands"], overrides, S=S)
    return f


# Component ablation set (E1). Names refer to what is switched OFF relative to full TASC-DEM.
def ablation_methods():
    full = dict()
    M = {
        "TASC-DEM": _tasc(full),
        "TASC-image": _tasc(dict(use_dem=False), None),
        "TASC-DEM/beta-only": _tasc_S_const(full, 0.0),      # w = beta everywhere: no spatial terrain information
        "TASC-image/no-DCT": _tasc(dict(use_dem=False, detail=False), None),
        "TASC-DEM/no-DCT": _tasc(dict(detail=False)),
        "TASC-image/per-band": _tasc(dict(use_dem=False, shared_gain=False), None),
        "TASC-image/hard-blocks": _tasc(dict(use_dem=False, smooth_field=False), None),
        "TASC-image/global-only": _tasc(dict(use_dem=False, grid=1, smooth_field=False, noise_aware=False), None),
        "TASC-image/no-global-exposure": _tasc(dict(use_dem=False, global_exposure=False), None),
    }
    return M


def classical_methods():
    M = {"Identity": lambda s: s["bands"].copy(),
         "GlobalGamma": lambda s: _shared(global_gamma_fn(), s["bands"]),
         "GlobalGamma-perband": lambda s: B.apply_per_band(lambda ch: global_gamma_fn()(ch), s["bands"]).astype(np.float32),
         "AGCWD+shared": lambda s: _shared(B.agcwd, s["bands"]),
         "CLAHE+shared": lambda s: _shared(B.clahe, s["bands"])}
    for name, fn in B.SINGLE_CHANNEL.items():
        M[name] = (lambda f: (lambda s: B.apply_per_band(f, s["bands"]).astype(np.float32)))(fn)
    return M


def build(profile: str, device="cpu"):
    """profile: 'rgb' (image-only datasets), 's2' (DEM available)."""
    M = classical_methods()
    try:
        z = ZeroDCETorch(device=device)
        M["Zero-DCE"] = z
    except Exception as e:  # recorded in coverage report
        M["Zero-DCE"] = None
        print("Zero-DCE unavailable:", e)
    M = {k: v for k, v in M.items() if v is not None}
    M["TASC-image"] = _tasc(dict(use_dem=False), None)
    if profile == "s2":
        M["TASC-DEM"] = _tasc(dict())
    return M
