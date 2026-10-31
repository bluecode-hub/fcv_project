"""TASC-Gamma: Terrain-Aware, Spectrally Consistent block-adaptive gamma correction.

Pipeline (all on luminance Y; the bands are touched once, at the end):

  0. Global exposure gamma     g0 = clip(ln tau / ln mean(Y), g_min, 1)
  1. Block gamma  (C1)         per block b of Y^g0 (16 px blocks by default): g_img(b) = clip(ln tau / ln mu_b, g_min, 1)
                               (upper bound 1 = bright-region protection)
  2. Terrain weighting (C2)    S = shadow likelihood from DEM hillshade + cast shadow
                               w = beta + (1 - beta) S ;  g_loc = 1 - w (1 - g_img)
  3. Seam-free field   (C1)    block values interpolated to pixels, then guided filter
                               Y_g = Y ** (g0 * g_loc)
  4. Detail boost      (C4)    detail D = Y_g - lowpass_DCT(Y_g);
                               Y_out = Y_g + (k(x) - 1) D, k smaller where Y was dark
  5. Shared gain       (C3)    G = Y_out / Y (capped so no band clips);  B'_k = G * B_k
                               -> NDVI, NDWI and any band ratio are unchanged.

Every component can be switched off for the ablation study.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import cv2
from scipy.fft import dctn, idctn

from .io_utils import luminance
from .terrain import illumination

EPS = 1e-4


@dataclass
class TASCConfig:
    tau: float = 0.55            # target mid-level (tuned on D2 val split)
    gamma_min: float = 0.40      # strongest allowed brightening
    block_px: int = 16           # block size in pixels (grid = image size / block_px)
    grid: int | None = None      # force an N x N grid instead (A0 uses grid=1)
    global_exposure: bool = True # step 0
    smooth_field: bool = True    # C1: interpolate + guided filter (False = hard blocks)
    gf_radius: int = 8
    gf_eps: float = 1e-3
    use_dem: bool = True         # C2
    beta: float = 0.30           # enhancement kept for dark-but-lit pixels
    gamma_min_shadow: float = 0.25  # lower gamma floor allowed where the DEM says shadow
    prior_sigma: float = 2.0     # smoothing of the per-pixel shadow likelihood (px)
    cast_shadow: bool = True
    shared_gain: bool = True     # C3 (False = apply gamma to every band separately)
    detail: bool = True          # C4
    k_max: float = 1.2
    noise_aware: bool = True     # C4: lower boost where Y was dark
    dct_cutoff: float = 0.12     # fraction of the spectrum kept as the base layer
    dark_object_subtraction: bool = False  # remove per-band haze offset first (TOA data)
    dos_percentile: float = 0.5
    dos_strength: float = 0.6    # fraction of the haze offset removed (1 = full DOS)

    def as_dict(self):
        return asdict(self)


def _block_means(y: np.ndarray, n: int) -> np.ndarray:
    """Mean of each block on an n (short side) x m grid of roughly square blocks."""
    H, W = y.shape
    nr, nc = (n, max(1, int(round(n * W / H)))) if H <= W else (max(1, int(round(n * H / W))), n)
    rs = np.linspace(0, H, nr + 1).astype(int)
    cs = np.linspace(0, W, nc + 1).astype(int)
    out = np.empty((nr, nc), np.float64)
    for i in range(nr):
        for j in range(nc):
            out[i, j] = y[rs[i]:rs[i + 1], cs[j]:cs[j + 1]].mean()
    return out


def _upsample(blocks: np.ndarray, shape, smooth: bool) -> np.ndarray:
    H, W = shape
    if smooth:  # bilinear between block centres (CLAHE-style)
        return cv2.resize(blocks.astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR)
    return cv2.resize(blocks.astype(np.float32), (W, H), interpolation=cv2.INTER_NEAREST)


def _gamma_from_mean(mu, tau, gmin):
    mu = np.clip(mu, 1e-3, 0.999)
    return np.clip(np.log(tau) / np.log(mu), gmin, 1.0)


def _guided(guide: np.ndarray, src: np.ndarray, r: int, eps: float) -> np.ndarray:
    if hasattr(cv2, "ximgproc"):
        return cv2.ximgproc.guidedFilter(guide.astype(np.float32), src.astype(np.float32), r, eps)
    # fallback: plain box-filter guided filter (He et al. 2010)
    I, p = guide.astype(np.float32), src.astype(np.float32)
    k = (2 * r + 1, 2 * r + 1)
    mI, mp = cv2.blur(I, k), cv2.blur(p, k)
    a = (cv2.blur(I * p, k) - mI * mp) / (cv2.blur(I * I, k) - mI * mI + eps)
    b = mp - a * mI
    return cv2.blur(a, k) * I + cv2.blur(b, k)


def dct_lowpass(y: np.ndarray, cutoff: float) -> np.ndarray:
    """Global 2-D DCT low-pass: keep coefficients with normalised radius < cutoff."""
    c = dctn(y.astype(np.float64), norm="ortho")
    H, W = y.shape
    u = np.arange(H)[:, None] / H
    v = np.arange(W)[None, :] / W
    c[np.hypot(u, v) >= cutoff] = 0.0
    return idctn(c, norm="ortho").astype(np.float32)


def shadow_likelihood(dem, dx, sun_az, sun_el, cast=True, sigma=2.0):
    """S in [0, 1]: 0 on flat / sun-facing ground, 1 in full (self or cast) shadow."""
    illum, _ = illumination(dem, dx, dx, sun_az, sun_el, with_cast_shadow=cast)
    S = np.clip(1.0 - illum, 0.0, 1.0)
    if sigma > 0:
        S = cv2.GaussianBlur(S, (0, 0), sigma)
    return S.astype(np.float32)


def dark_object_subtraction(bands: np.ndarray, pct: float = 0.5, strength: float = 1.0) -> np.ndarray:
    """Chavez-style haze removal: subtract each band's darkest-object value.

    TOA data carries an additive path-radiance offset (largest in blue). A shared gain
    keeps band ratios, so without this step it also keeps the haze ratio and shadows
    turn blue. Ratios after DOS are closer to surface reflectance ratios.
    """
    valid = bands.max(-1) > 0
    off = np.array([np.percentile(bands[..., k][valid], pct) for k in range(bands.shape[-1])], np.float32)
    return np.clip(bands - strength * off, 0, 1)


def soft_knee_gain(G: np.ndarray, bands: np.ndarray, knee: float = 0.85, top: float = 0.97) -> np.ndarray:
    """Compress the gain where the brightest band would pass ``knee``.

    The brightest band m = G * max_k(B_k) is mapped through a smooth knee that
    approaches ``top`` < 1 instead of clipping. The correction is one factor per pixel,
    so band ratios (and NDVI etc.) are still unchanged.
    """
    mb = np.maximum(bands.max(-1), EPS)
    m = G * mb
    room = top - knee
    m2 = np.where(m > knee, knee + room * np.tanh((m - knee) / room), m)
    return (G * m2 / np.maximum(m, EPS)).astype(np.float32)


class TASCGamma:
    def __init__(self, cfg: TASCConfig | None = None, **overrides):
        self.cfg = cfg or TASCConfig()
        for k, v in overrides.items():
            setattr(self.cfg, k, v)

    def __call__(self, bands: np.ndarray, dem=None, dx=None, sun_az=None, sun_el=None, return_maps=False):
        """Enhance a [H, W, K] reflectance-like array in [0, 1] (band order B, G, R, NIR...)."""
        c = self.cfg
        bands = bands.astype(np.float32)
        if c.dark_object_subtraction:
            bands = dark_object_subtraction(bands, c.dos_percentile, c.dos_strength)
        Y = np.clip(luminance(bands), EPS, 1.0)

        # 0. global exposure
        g0 = float(_gamma_from_mean(Y.mean(), c.tau, c.gamma_min)) if c.global_exposure else 1.0
        Yg0 = Y ** g0

        # 1. block gamma (image-based)
        n = c.grid or max(1, int(round(min(Y.shape) / c.block_px)))
        g_blocks = _gamma_from_mean(_block_means(Yg0, n), c.tau, c.gamma_min)
        g_img = _upsample(g_blocks, Y.shape, c.smooth_field)

        # 2. terrain weighting
        if c.use_dem and dem is not None and sun_az is not None:
            S = shadow_likelihood(dem, dx, sun_az, sun_el, c.cast_shadow, c.prior_sigma)
            w = c.beta + (1.0 - c.beta) * S
            # In terrain shadow the block mean (which mixes lit and shadowed pixels)
            # under-estimates the needed lift: recompute gamma from the local mean of
            # the shadowed pixels themselves and allow a lower floor there.
            mu_sh = cv2.blur(Yg0, (c.block_px + 1, c.block_px + 1))
            floor = c.gamma_min - (c.gamma_min - c.gamma_min_shadow) * S
            g_sh = np.clip(np.log(c.tau) / np.log(np.clip(mu_sh * (1 - 0.7 * S), 1e-3, 0.999)), floor, 1.0)
            g_img = (1 - S) * g_img + S * g_sh
        else:
            S = None
            w = np.ones_like(Y)
            floor = c.gamma_min
        g_loc = 1.0 - w * (1.0 - g_img)

        # 3. seam-free field
        if c.smooth_field:
            g_loc = np.clip(_guided(Yg0, g_loc, c.gf_radius, c.gf_eps), floor, 1.0)
        gamma = (g0 * g_loc).astype(np.float32)

        if not c.shared_gain:
            # Ablation A5: same gamma field applied to every band independently.
            out = np.clip(bands, EPS, 1.0) ** gamma[..., None]
            if c.detail:
                Yo = luminance(out)
                Yd = self._detail(Yo, Y)
                out = out * (Yd / np.maximum(Yo, EPS))[..., None]
            out = np.clip(out, 0, 1)
            return (out, dict(gamma=gamma, S=S)) if return_maps else out

        Yg = Y ** gamma

        # 4. detail boost
        Y_out = self._detail(Yg, Y) if c.detail else Yg

        # 5. shared gain with a soft highlight knee (same factor for every band)
        G = np.maximum(Y_out, 0) / Y
        G = soft_knee_gain(G, bands)
        out = np.clip(bands * G[..., None], 0, 1)
        if return_maps:
            return out, dict(gamma=gamma, S=S, gain=G)
        return out

    def _detail(self, Yg, Y):
        c = self.cfg
        base = dct_lowpass(Yg, c.dct_cutoff)
        D = Yg - base
        if c.noise_aware:
            # gain falls in pixels that were dark before enhancement (noise lives there)
            lit = cv2.GaussianBlur(Y, (0, 0), 4.0)
            k = 1.0 + (c.k_max - 1.0) * np.clip(lit / c.tau, 0.0, 1.0) ** 0.5
        else:
            k = np.full_like(Y, c.k_max)
        return np.clip(Yg + (k - 1.0) * D, 0.0, 1.0)


# Named ablation variants (see the problem statement, "Baselines and ablations").
ABLATIONS = {
    "A0_global_gamma_dct": dict(grid=1, smooth_field=False, use_dem=False, noise_aware=False),
    "A1_hard_blocks": dict(smooth_field=False, use_dem=False, detail=False),
    "A2_smooth_field": dict(use_dem=False, detail=False),
    "A3_plus_dem": dict(detail=False),
    "A4_full": dict(),
    "A5_full_per_band": dict(shared_gain=False),
    "A4_no_dem": dict(use_dem=False),
}
