"""Evaluation metrics: full-reference, no-reference, region-level, spectral, artifacts."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import cv2
from scipy.io import loadmat
from scipy.ndimage import correlate
from scipy.special import gamma as G
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

from .io_utils import luminance, ndvi, ndwi, to_rgb8

MODELS = Path(__file__).parent / "iqa_models"
EPS = 1e-6


# ----------------------------------------------------------------- basic quality
def psnr(out, gt):
    return float(peak_signal_noise_ratio(gt, out, data_range=1.0))


def ssim(out, gt):
    return float(structural_similarity(gt, out, data_range=1.0, channel_axis=-1))


def entropy(y, mask=None):
    v = y[mask] if mask is not None else y.ravel()
    if v.size < 50:
        return np.nan
    h = np.bincount(np.clip((v * 255).round().astype(int), 0, 255), minlength=256).astype(np.float64)
    p = h[h > 0] / h.sum()
    return float(-(p * np.log2(p)).sum())


def eme(y, block=8, c=1 / 255):
    """Agaian's measure of enhancement, 20*log10(max/min) averaged over blocks."""
    H, W = (y.shape[0] // block) * block, (y.shape[1] // block) * block
    b = y[:H, :W].reshape(H // block, block, W // block, block)
    mx, mn = b.max((1, 3)), b.min((1, 3))
    return float(np.mean(20 * np.log10((mx + c) / (mn + c))))


def avg_gradient(y):
    gx = np.diff(y, axis=1)[:-1, :]
    gy = np.diff(y, axis=0)[:, :-1]
    return float(np.mean(np.sqrt((gx ** 2 + gy ** 2) / 2)))


# ----------------------------------------------------------------- NIQE
_GAM = np.arange(0.2, 10.0001, 0.001)
_R_GAM = G(2 / _GAM) ** 2 / (G(1 / _GAM) * G(3 / _GAM))


def _aggd(v):
    v = v.ravel()
    left = np.sqrt(np.mean(v[v < 0] ** 2)) if (v < 0).any() else EPS
    right = np.sqrt(np.mean(v[v > 0] ** 2)) if (v > 0).any() else EPS
    gh = left / right
    rhat = np.mean(np.abs(v)) ** 2 / np.mean(v ** 2)
    rn = rhat * (gh ** 3 + 1) * (gh + 1) / (gh ** 2 + 1) ** 2
    a = _GAM[np.argmin((_R_GAM - rn) ** 2)]
    k = np.sqrt(G(1 / a) / G(3 / a))
    return a, left * k, right * k


def _block_feats(s):
    # Feature layout of scikit-video's NIQE, which produced niqe_image_params.mat
    # (note: the diagonal orientations repeat the left scale, as in that code).
    a, bl, br = _aggd(s)
    f = [a, (bl + br) / 2]
    for i, sh in enumerate([(0, 1), (1, 0), (1, 1), (1, -1)]):
        p = s * np.roll(s, sh, axis=(0, 1))
        a, bl, br = _aggd(p)
        n = (br - bl) * (G(2 / a) / G(1 / a))
        f += [a, n, bl, br] if i < 2 else [a, n, bl, bl]
    return f


def _mscn(im):
    x = np.arange(-3, 4)
    g = np.exp(-(x[:, None] ** 2 + x[None, :] ** 2) / (2 * (7 / 6) ** 2))
    g /= g.sum()
    mu = correlate(im, g, mode="constant")
    sd = np.sqrt(np.abs(correlate(im * im, g, mode="constant") - mu * mu))
    return (im - mu) / (sd + 1)


def _half(im):
    from PIL import Image
    h, w = im.shape
    return np.asarray(Image.fromarray(im.astype(np.float32), "F").resize((w // 2, h // 2), Image.BICUBIC),
                      dtype=np.float64)


@lru_cache(1)
def _niqe_model():
    m = loadmat(MODELS / "niqe_image_params.mat")
    return m["pop_mu"].ravel(), m["pop_cov"]


def niqe(rgb8, block=96):
    """NIQE (Mittal et al. 2013), lower is better. Follows the original MATLAB code."""
    mu_p, cov_p = _niqe_model()
    im = luminance(rgb8[..., ::-1].astype(np.float64)) if rgb8.ndim == 3 else rgb8.astype(np.float64)
    # luminance() expects B,G,R,(NIR) order; rgb8 is R,G,B -> reversed above
    H, W = (im.shape[0] // block) * block, (im.shape[1] // block) * block
    im = im[:H, :W]
    feats = []
    for scale, bs in [(1, block), (2, block // 2)]:
        x = im if scale == 1 else _half(im)
        s = _mscn(x)
        f = [_block_feats(s[i:i + bs, j:j + bs]) for i in range(0, s.shape[0] - bs + 1, bs)
             for j in range(0, s.shape[1] - bs + 1, bs)]
        feats.append(np.array(f))
    F = np.hstack(feats)
    mu_d = np.nanmean(F, 0)
    cov_d = np.cov(F, rowvar=False) if F.shape[0] > 1 else np.zeros((F.shape[1], F.shape[1]))
    d = mu_p - mu_d
    return float(np.sqrt(d @ np.linalg.pinv((cov_p + cov_d) / 2) @ d))


def brisque(rgb8):
    """BRISQUE via OpenCV's quality module with the LIVE model (lower is better)."""
    gray = cv2.cvtColor(rgb8, cv2.COLOR_RGB2GRAY)
    s = cv2.quality.QualityBRISQUE_compute(gray, str(MODELS / "brisque_model_live.yml"),
                                           str(MODELS / "brisque_range_live.yml"))
    return float(s[0])


# ----------------------------------------------------------------- spectral
def sam_deg(a, b, mask=None):
    num = (a * b).sum(-1)
    den = np.linalg.norm(a, axis=-1) * np.linalg.norm(b, axis=-1) + EPS
    ang = np.rad2deg(np.arccos(np.clip(num / den, -1, 1)))
    return float(ang[mask].mean() if mask is not None else ang.mean())


def index_mae(a, b, fn, mask):
    return float(np.abs(fn(a) - fn(b))[mask].mean())


# ----------------------------------------------------------------- artifacts
def blockiness(y_out, y_in, period=32):
    """Seam score: (boundary/interior gradient ratio of output) / (same for input).

    1.0 = no new seams on the block grid; > 1 = visible block boundaries.
    """
    def ratio(y):
        gx = np.abs(np.diff(y, axis=1))
        gy = np.abs(np.diff(y, axis=0))
        cb = np.arange(period - 1, gx.shape[1], period)
        rb = np.arange(period - 1, gy.shape[0], period)
        bx = gx[:, cb].mean()
        by = gy[rb, :].mean()
        ix = np.delete(gx, cb, axis=1).mean()
        iy = np.delete(gy, rb, axis=0).mean()
        return (bx + by) / (ix + iy + EPS)
    return float(ratio(y_out) / (ratio(y_in) + EPS))


# ----------------------------------------------------------------- region masks for real data
def real_masks(bands, S):
    """Masks for real tiles from the terrain shadow likelihood S and spectral indices."""
    Y = luminance(bands)
    lit = S <= 0.10
    m = dict(
        shadow=S >= 0.5,
        lit=lit,
        bright=lit & (Y >= 0.25),                                    # snow, granite, playa
        dark_material=lit & ((ndwi(bands) > 0.1) | (ndvi(bands) > 0.35)) & (Y <= np.percentile(Y, 30)),
    )
    return m


def _mean(x, m):
    return float(x[m].mean()) if m.sum() >= 50 else np.nan


# ----------------------------------------------------------------- per-dataset metric sets
def metrics_real(out, inp, masks, nr=("brisque",)):
    Yo, Yi = luminance(out), luminance(inp)
    valid = Yi > 0.01
    lift_sh = _mean(Yo - Yi, masks["shadow"])
    lift_dm = _mean(Yo - Yi, masks["dark_material"])
    r = dict(
        entropy=entropy(Yo), eme=eme(Yo), avg_grad=avg_gradient(Yo), mean_Y=float(Yo.mean()),
        shadow_entropy=entropy(Yo, masks["shadow"]),
        shadow_lift=lift_sh,
        bright_clip=_mean((out.max(-1) >= 0.98).astype(np.float32), masks["bright"]),
        bright_lift=_mean(Yo - Yi, masks["bright"]),
        darkmat_lift=lift_dm,
        darkmat_to_shadow=(lift_dm / lift_sh) if (lift_sh and lift_sh > 1e-3 and not np.isnan(lift_dm)) else np.nan,
        ndvi_mae=index_mae(out, inp, ndvi, valid), ndwi_mae=index_mae(out, inp, ndwi, valid),
        sam=sam_deg(out, inp, valid), blockiness=blockiness(Yo, Yi),
    )
    rgb8 = to_rgb8(out)
    if "niqe" in nr:
        r["niqe"] = niqe(rgb8)
    if "brisque" in nr:
        r["brisque"] = brisque(rgb8)
    return r


def metrics_synth(out, inp, gt, masks, nr=("brisque",)):
    Yo, Yi, Yg = luminance(out), luminance(inp), luminance(gt)
    valid = Yg > 0.01
    err = np.abs(Yo - Yg)
    r = dict(
        psnr=psnr(out, gt), ssim=ssim(out, gt), ambe=float(abs(Yo.mean() - Yg.mean())),
        entropy=entropy(Yo), eme=eme(Yo),
        mae_shadow=_mean(err, masks["shadow"]), mae_lit=_mean(err, masks["lit"]),
        mae_darkmat=_mean(err, masks["dark_material"]), mae_cloud=_mean(err, masks["cloud_shadow"]),
        overshoot_lit=_mean(np.maximum(Yo - Yg, 0), masks["lit"]),
        clip_lit=_mean((out.max(-1) >= 0.98).astype(np.float32) * (gt.max(-1) < 0.98), masks["lit"]),
        ndvi_mae_vs_gt=index_mae(out, gt, ndvi, valid), sam_vs_gt=sam_deg(out, gt, valid),
        blockiness=blockiness(Yo, Yi),
    )
    rgb8 = to_rgb8(out)
    if "niqe" in nr:
        r["niqe"] = niqe(rgb8)
    if "brisque" in nr:
        r["brisque"] = brisque(rgb8)
    return r
