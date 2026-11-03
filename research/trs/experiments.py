"""Experiment stages (E1-E8). Every stage appends rows to a Store, so it can be resumed."""
from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

import numpy as np

from . import paths, methods as MT, metrics2 as MX
from .adapter import run_tasc
from .store import Store, Timer
from tasc.io_utils import luminance


# ------------------------------------------------------------------ method sets
def s2_methods(device="cpu"):
    M = MT.build("s2", device)
    M.pop("TASC-DEM", None)
    t = MT._tasc
    M["TASC-DEM"] = t({})
    M["TASC-DEM/no-DCT"] = t(dict(detail=False))
    M["TASC-DEM/beta-only"] = MT._tasc_S_const({}, 0.0)
    M["TASC-DEM/wrong-DEM"] = t({}, "wrong")
    M["TASC-DEM/shift300m"] = t({}, "shift30")
    M["TASC-DEM/shift1km"] = t({}, "shift100")
    for k, lab in [("az+15", "az+15"), ("az-15", "az-15"), ("el+7", "el+7"), ("el-7", "el-7")]:
        M[f"TASC-DEM/{lab}"] = t({}, k)
    M["TASC-image/no-DCT"] = t(dict(use_dem=False, detail=False), None)
    M["TASC-image/per-band"] = t(dict(use_dem=False, shared_gain=False), None)
    M["TASC-DEM/per-band"] = t(dict(shared_gain=False))
    M["TASC-image/hard-blocks"] = t(dict(use_dem=False, smooth_field=False), None)
    M["TASC-image/global-only"] = t(dict(use_dem=False, grid=1, smooth_field=False, noise_aware=False), None)
    M["C-correction"] = lambda s: MT.terrain_correction(s["bands"], s["cos_i"], s["cos_z"], s["slope"], "C")
    M["SCS+C"] = lambda s: MT.terrain_correction(s["bands"], s["cos_i"], s["cos_z"], s["slope"], "SCS+C")
    return M


def rgb_methods(device="cpu", ablations=False):
    M = MT.build("rgb", device)
    if ablations:
        for k, v in MT.ablation_methods().items():
            if "DEM" not in k:
                M[k] = v
    return M


# ------------------------------------------------------------------ generic loop
def run_samples(samples, methods, store: Store, metric_fn, log=print, only=None):
    n = 0
    for s in samples:
        todo = [m for m in methods if not store.has(s["name"], m) and (only is None or m in only)]
        if not todo:
            continue
        for m in todo:
            f = methods[m]
            try:
                with Timer() as t:
                    out = np.clip(np.asarray(f(s), np.float32), 0, 1)
                row = metric_fn(out, s)
                mp = s["bands"].shape[0] * s["bands"].shape[1] / 1e6
                store.add(sample=s["name"], method=m, group=s.get("group"), ms_per_mp=t.dt * 1e3 / mp,
                          status="ok", **row)
            except Exception as e:
                store.add(sample=s["name"], method=m, group=s.get("group"), status=f"fail: {type(e).__name__}: {e}")
                log(f"  FAIL {s['name']} {m}: {e}")
                if "--debug" in __import__("sys").argv:
                    traceback.print_exc()
            n += 1
        log(f"  {s['name']}: {len(todo)} methods")
    return n


# ------------------------------------------------------------------ metric functions
def metric_s2(out, s):
    inp = s["bands"]
    r = MX.common_nr(out, inp, nr=("brisque", "niqe"))
    r.update(MX.spectral_vs_input(out, inp, s["valid"]))
    r.update(MX.region_response(out, inp, s["S"], s["scl"], s["valid"]))
    r.update(region=s["region"], scene=s["scene"], split=s["split"])
    return r


def metric_paired(out, s):
    r = MX.paired(out, s["bands"], s["gt"], with_lpips=True)
    r.update(MX.spectral_vs_input(out, s["bands"]) if out.shape[-1] > 3 else {})
    r["source"] = s.get("source")
    r["degradation"] = s.get("degradation")
    return r


def metric_nr(out, s):
    r = MX.common_nr(out, s["bands"], nr=("brisque", "niqe"))
    r["source"] = s.get("source")
    return r


def metric_d2(out, s):
    from tasc import metrics as M0
    masks = {k: s[f"mask_{k}"] for k in ["shadow", "lit", "dark_material", "cloud_shadow"]}
    r = M0.metrics_synth(out, s["bands"], s["gt"], masks, nr=())
    r["lpips"] = MX.lpips_dist(out, s["gt"])
    r["halo"] = MX.gradient_reversal(luminance(out), luminance(s["bands"]))
    r["noise_amp"] = MX.noise_amplification(luminance(out), luminance(s["bands"]))
    return r


def rgb_abl_methods(device="cpu"):
    return rgb_methods(device, ablations=True)


def d2_methods(device="cpu"):
    """Landsat D2 (GT available): frozen v0 reproduction, v0 ablations, baselines and geometry controls."""
    from tasc.method import TASCGamma, ABLATIONS
    M = MT.build("rgb", device)
    M.pop("TASC-image", None)

    M["TASC-v0"] = lambda s: TASCGamma()(s["bands"], s["dem"], s["dx"], s["sun_az"], s["sun_el"])
    for k, ov in ABLATIONS.items():
        if k != "A4_full":
            M[k] = (lambda ov: (lambda s: TASCGamma(**ov)(s["bands"], s["dem"], s["dx"], s["sun_az"], s["sun_el"])))(ov)
    M["TASC-DEM/beta-only"] = lambda s: run_tasc(s["bands"], {}, S=np.zeros(s["bands"].shape[:2], np.float32))
    M["TASC-DEM/no-DCT"] = lambda s: TASCGamma(detail=False)(s["bands"], s["dem"], s["dx"], s["sun_az"], s["sun_el"])

    def shifted(px):
        return lambda s: TASCGamma()(s["bands"], np.roll(s["dem"], px, axis=1), s["dx"], s["sun_az"], s["sun_el"])
    M["TASC-DEM/shift4px(720m)"] = shifted(4)
    M["TASC-DEM/shift16px(2.9km)"] = shifted(16)
    M["TASC-DEM/flipped-DEM"] = lambda s: TASCGamma()(s["bands"], s["dem"][::-1].copy(), s["dx"], s["sun_az"], s["sun_el"])
    for lab, da, de in [("az+15", 15, 0), ("az-15", -15, 0), ("az+45", 45, 0), ("el+7", 0, 7), ("el-7", 0, -7)]:
        M[f"TASC-DEM/{lab}"] = (lambda da, de: (lambda s: TASCGamma()(
            s["bands"], s["dem"], s["dx"], (s["sun_az"] + da) % 360, float(np.clip(s["sun_el"] + de, 3, 85)))))(da, de)
    return M


# ------------------------------------------------------------------ corrected spectral metrics (correction pass)
def _spectral_block(out, ref, valid, prefix=""):
    """SAM, NDVI/NDWI error and band-ratio deviation of `out` against `ref`, corrected validity handling; 4-band input."""
    from . import spectral as SP
    r = {}
    sm = SP.sam_deg_valid(out, ref, valid)
    r.update({f"{prefix}sam": sm["sam"], f"{prefix}n_used": sm["n_used"], f"{prefix}n_valid_mask": sm["n_valid_mask"],
              f"{prefix}n_excl_norm": sm["n_excl_norm"], f"{prefix}n_excl_invalid": sm["n_excl_invalid"],
              f"{prefix}frac_used": sm["frac_used"]})
    r[f"{prefix}sam_t03"] = SP.sam_deg_valid(out, ref, valid, SP.MIN_NORM_SENS)["sam"]
    if out.shape[-1] >= 4:
        r[f"{prefix}ndvi_mae"], r[f"{prefix}ndvi_n"], _ = SP.nd_index_mae_valid(out, ref, 3, 2, valid)
        r[f"{prefix}ndwi_mae"], _, _ = SP.nd_index_mae_valid(out, ref, 1, 3, valid)
        r[f"{prefix}band_ratio_dev"], r[f"{prefix}ratio_n"], _ = SP.band_ratio_dev_valid(out, ref, valid)
    return r


def metric_s2_sam(out, s):
    """Sentinel-2: corrected spectral preservation of the output relative to the INPUT."""
    r = _spectral_block(out, s["bands"], s["valid"])
    r.update(region=s["region"], scene=s["scene"], split=s["split"])
    return r


def metric_d2_sam(out, s):
    """Landsat D2: corrected spectral reconstruction accuracy against the clean reference (vsgt_*) and preservation
    relative to the degraded input (vsinp_*)."""
    r = _spectral_block(out, s["gt"], None, "vsgt_")
    r.update(_spectral_block(out, s["bands"], None, "vsinp_"))
    r["sam_vs_gt"], r["sam_vs_input"] = r["vsgt_sam"], r["vsinp_sam"]
    r["ndvi_mae_vs_gt"] = r["vsgt_ndvi_mae"]
    return r


# ------------------------------------------------------------------ Phase 4: TASC-v1 method sets (frozen v0 kept as reference)
def _p4_common(device="cpu"):
    """Only the v0 reference rows are recomputed (Identity too, as a cross-check of the Phase 3 store); all other baselines
    (Zero-DCE, CLAHE, global gamma ...) are read from the Phase 3 stores, which use identical sample keys and inputs."""
    return {"Identity": lambda s: s["bands"].copy(),
            "TASC-v0": lambda s: run_tasc(s["bands"], dict(use_dem=False)),
            "TASC-v0/no-global-exposure": lambda s: run_tasc(s["bands"], dict(use_dem=False, global_exposure=False))}


def p4_rgb_methods(device="cpu"):
    """AID / iSAID-dark / DarkRS / ExDark: image-only methods (no DEM)."""
    from ..v1.registry import v1_methods
    M = _p4_common(device)
    M.update(v1_methods(include_ablations=True, dem=False))
    return M


def p4_s2_methods(device="cpu"):
    """Sentinel-2 + GLO-30: samples carry the context-aware shadow field S plus control fields (wrong / shifted / sun)."""
    from ..v1.registry import v1_methods
    from ..v1.config import CANDIDATES, variant
    from ..v1.method import TASCv1
    M = _p4_common(device)
    M["TASC-v0-DEM"] = MT._tasc({})
    M.update(v1_methods(include_ablations=True, dem=True))
    c3 = CANDIDATES["C3_local_dem"]
    for lab, key in [("wrong-DEM", "wrong"), ("shift300m", "shift30"), ("shift1km", "shift100"),
                     ("az+15", "az+15"), ("az-15", "az-15"), ("el+7", "el+7"), ("el-7", "el-7")]:
        M[f"C3/{lab}"] = (lambda key: (lambda s: TASCv1(variant(c3))(s["bands"], S=s[key])))(key)
    return M


def p4_d2_methods(device="cpu"):
    """Landsat D2 (GT available): v0 reference + v1 candidates with the DEM/sun inputs and geometry controls."""
    from ..v1.config import CANDIDATES, variant
    from ..v1.method import TASCv1
    from tasc.method import TASCGamma
    M = _p4_common(device)
    M["TASC-v0-DEM"] = lambda s: TASCGamma()(s["bands"], s["dem"], s["dx"], s["sun_az"], s["sun_el"])
    M["C1_exposure"] = lambda s: TASCv1(variant(CANDIDATES["C1_exposure"]))(s["bands"])
    M["C2_local_image"] = lambda s: TASCv1(variant(CANDIDATES["C2_local_image"]))(s["bands"])
    c3 = CANDIDATES["C3_local_dem"]
    M["C3_local_dem"] = lambda s: TASCv1(variant(c3))(s["bands"], s["dem"], s["dx"], s["sun_az"], s["sun_el"])
    M["C3/no-trust"] = lambda s: TASCv1(variant(c3, rho0=-2.0, rho1=-1.99))(s["bands"], s["dem"], s["dx"], s["sun_az"], s["sun_el"])
    M["C3/+DCT-detail"] = lambda s: TASCv1(variant(c3, detail=True))(s["bands"], s["dem"], s["dx"], s["sun_az"], s["sun_el"])
    M["C3/per-band"] = lambda s: TASCv1(variant(c3, shared_gain=False))(s["bands"], s["dem"], s["dx"], s["sun_az"], s["sun_el"])
    M["C3/no-exposure"] = lambda s: TASCv1(variant(c3, exposure=False))(s["bands"], s["dem"], s["dx"], s["sun_az"], s["sun_el"])
    for px in (4, 16):
        M[f"C3/shift{px}px"] = (lambda px: (lambda s: TASCv1(variant(c3))(
            s["bands"], np.roll(s["dem"], px, axis=1), s["dx"], s["sun_az"], s["sun_el"])))(px)
    M["C3/flipped-DEM"] = lambda s: TASCv1(variant(c3))(s["bands"], s["dem"][::-1].copy(), s["dx"], s["sun_az"], s["sun_el"])
    for lab, da, de in [("az+15", 15, 0), ("az+45", 45, 0), ("el+7", 0, 7), ("el-7", 0, -7)]:
        M[f"C3/{lab}"] = (lambda da, de: (lambda s: TASCv1(variant(c3))(
            s["bands"], s["dem"], s["dx"], (s["sun_az"] + da) % 360, float(np.clip(s["sun_el"] + de, 3, 85)))))(da, de)
    return M
