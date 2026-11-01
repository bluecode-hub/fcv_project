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
