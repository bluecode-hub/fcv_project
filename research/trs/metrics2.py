"""Metrics used by the research experiments. Wraps the frozen v0 metrics and adds LPIPS, halo,
noise amplification, highlight distortion (mask defined on the REFERENCE/INPUT, never the output)
and shadow/dark-surface equalisation scores."""
from __future__ import annotations

import cv2
import numpy as np

from tasc import metrics as M0
from tasc.io_utils import luminance, to_rgb8, ndvi, ndwi

_lp = {}


def lpips_dist(out, ref):
    """LPIPS (AlexNet) between two BGR(+NIR) arrays; uses RGB channels only."""
    import torch, lpips
    if "net" not in _lp:
        _lp["net"] = lpips.LPIPS(net="alex", verbose=False).eval()
    f = lambda a: torch.from_numpy(np.ascontiguousarray(a[..., [2, 1, 0]].transpose(2, 0, 1)))[None].float() * 2 - 1
    with torch.no_grad():
        return float(_lp["net"](f(out), f(ref)))


def noise_sigma(y):
    """Immerkaer (1996) fast noise-level estimate on a [0,1] luminance image."""
    k = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    c = cv2.filter2D(y.astype(np.float32), -1, k)[1:-1, 1:-1]
    h, w = y.shape
    return float(np.sqrt(np.pi / 2) / (6.0 * (w - 2) * (h - 2)) * np.abs(c).sum())


def noise_amplification(yo, yi):
    """sigma(out) / (mean gain * sigma(in)); 1 = noise grows only with the signal gain."""
    gain = max(float(yo.mean() / max(yi.mean(), 1e-4)), 1e-3)
    return noise_sigma(yo) / (gain * max(noise_sigma(yi), 1e-5))


def gradient_reversal(yo, yi, edge_q=90):
    """Halo indicator: fraction of strong-edge-neighbourhood pixels where the horizontal or vertical
    gradient changes sign between input and output (0 = no reversal)."""
    gx_i, gy_i = np.diff(yi, axis=1)[:-1], np.diff(yi, axis=0)[:, :-1]
    gx_o, gy_o = np.diff(yo, axis=1)[:-1], np.diff(yo, axis=0)[:, :-1]
    mag = np.hypot(gx_i, gy_i)
    strong = mag >= np.percentile(mag, edge_q)
    strong = cv2.dilate(strong.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    rev = ((gx_i * gx_o < 0) & (np.abs(gx_i) > 0.01)) | ((gy_i * gy_o < 0) & (np.abs(gy_i) > 0.01))
    return float(rev[strong].mean()) if strong.any() else np.nan


def _mean(x, m):
    return float(x[m].mean()) if m is not None and m.sum() >= 50 else np.nan


def common_nr(out, inp, nr=("brisque",)):
    Yo, Yi = luminance(out), luminance(inp)
    r = dict(entropy=M0.entropy(Yo), eme=M0.eme(Yo), avg_grad=M0.avg_gradient(Yo), mean_Y=float(Yo.mean()),
             blockiness=M0.blockiness(Yo, Yi), halo=gradient_reversal(Yo, Yi),
             noise_amp=noise_amplification(Yo, Yi))
    rgb8 = to_rgb8(out)
    if "brisque" in nr:
        r["brisque"] = M0.brisque(rgb8)
    if "niqe" in nr:
        r["niqe"] = M0.niqe(rgb8)
    return r


def paired(out, inp, gt, with_lpips=True, bright_thr=0.7, dark_thr=0.15):
    """Full-reference metrics. Regions come from the REFERENCE: dark = Y_gt-independent?  no -
    'shadow-like' regions are the darkest quartile of the INPUT relative to the reference (largest
    degradation), bright = reference highlights."""
    Yo, Yi, Yg = luminance(out), luminance(inp), luminance(gt)
    err = np.abs(Yo - Yg)
    dark_in = Yi <= np.percentile(Yi, 25)
    bright = Yg >= bright_thr
    r = dict(psnr=M0.psnr(out[..., :3], gt[..., :3]), ssim=M0.ssim(out[..., :3], gt[..., :3]),
             mae=float(err.mean()), mae_dark_in=_mean(err, dark_in), mae_bright=_mean(err, bright),
             bright_clip_new=_mean(((out.max(-1) >= 0.98) & (gt.max(-1) < 0.98)).astype(np.float32), bright),
             overshoot_bright=_mean(np.maximum(Yo - Yg, 0), bright),
             ambe=float(abs(Yo.mean() - Yg.mean())))
    if out.shape[-1] > 3:
        v = Yg > 0.01
        r["ndvi_mae_vs_gt"] = M0.index_mae(out, gt, ndvi, v)
        r["sam_vs_gt"] = M0.sam_deg(out, gt, v)
    if with_lpips:
        r["lpips"] = lpips_dist(out, gt)
    r.update(common_nr(out, inp, nr=()))
    return r


def spectral_vs_input(out, inp, valid=None):
    v = (luminance(inp) > 0.01) if valid is None else valid
    r = dict(sam=M0.sam_deg(out, inp, v))
    if out.shape[-1] >= 4:
        r.update(ndvi_mae=M0.index_mae(out, inp, ndvi, v), ndwi_mae=M0.index_mae(out, inp, ndwi, v))
    # band-ratio stability: mean |log((o_i/o_j)/(i_i/i_j))| over band pairs
    e = 1e-4
    lr = []
    for a in range(out.shape[-1]):
        for b in range(a + 1, out.shape[-1]):
            lr.append(np.abs(np.log((out[..., a] + e) / (out[..., b] + e)) - np.log((inp[..., a] + e) / (inp[..., b] + e)))[v].mean())
    r["band_ratio_dev"] = float(np.mean(lr))
    return r


def region_response(out, inp, S, scl=None, valid=None):
    """E2 metrics on Sentinel-2 tiles. Masks use a DEM-derived shadow PROXY (S) and are NOT ground truth;
    material classes come from spectral indices, which are independent of the DEM."""
    Yo, Yi = luminance(out), luminance(inp)
    ok = np.ones_like(Yi, bool) if valid is None else valid.copy()
    if scl is not None:
        ok &= ~np.isin(scl, [0, 1, 3, 8, 9, 10])      # exclude nodata, saturated, cloud shadow, clouds (snow kept)
    nd, nw = ndvi(inp) if inp.shape[-1] > 3 else None, ndwi(inp) if inp.shape[-1] > 3 else None
    sh = ok & (S >= 0.5)
    lit = ok & (S <= 0.1)
    bright = lit & (Yi >= 0.25)
    water = lit & (nw > 0.1) if nw is not None else None
    forest = lit & (nd > 0.35) & (Yi <= np.percentile(Yi[ok], 30)) if nd is not None else None
    dark_lit = lit & (Yi <= np.percentile(Yi[ok], 25))
    d = Yo - Yi
    res = dict(lift_shadow=_mean(d, sh), lift_dark_lit=_mean(d, dark_lit), lift_water=_mean(d, water),
               lift_forest=_mean(d, forest), lift_bright=_mean(d, bright),
               bright_clip=_mean((out.max(-1) >= 0.98).astype(np.float32), bright),
               bright_compress=_mean(np.maximum(Yi - Yo, 0), bright))
    ls, ld = res["lift_shadow"], res["lift_dark_lit"]
    res["dark_to_shadow_lift"] = (ld / ls) if (ls and ls > 1e-3 and not np.isnan(ld)) else np.nan
    # material-matched illumination equalisation: same-material pixels (vegetation) in shadow vs lit
    if nd is not None:
        veg = ok & (nd > 0.5)
        a, b = _mean(Yi, veg & (S >= 0.5)), _mean(Yi, veg & (S <= 0.1))
        a2, b2 = _mean(Yo, veg & (S >= 0.5)), _mean(Yo, veg & (S <= 0.1))
        res["veg_shadow_lit_ratio_in"] = a / b if b else np.nan
        res["veg_shadow_lit_ratio_out"] = a2 / b2 if b2 else np.nan
        res["equalisation_gain"] = (abs(np.log(a / b)) - abs(np.log(a2 / b2))) if (a and b and a2 and b2) else np.nan
    res["shadow_px_frac"] = float(sh.mean())
    return res
