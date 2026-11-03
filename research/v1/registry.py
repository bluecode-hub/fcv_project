"""Named TASC-v1 variants for experiments. Each value is ``f(sample) -> float32 [H, W, K]`` like research/trs/methods.py.
A sample may carry ``S`` (context-aware geometric shadow field, as in Phase 3) or ``dem/dx/sun_az/sun_el``."""
from __future__ import annotations

from .config import V1Config, CANDIDATES, variant
from .method import TASCv1


def _mk(cfg: V1Config, dem=False):
    def f(s):
        t = TASCv1(variant(cfg))
        if dem and s.get("S") is not None:
            return t(s["bands"], S=s["S"])
        if dem and s.get("dem") is not None:
            return t(s["bands"], s["dem"], s["dx"], s["sun_az"], s["sun_el"])
        return t(s["bands"])
    return f


def v1_methods(include_ablations=True, dem=False):
    base = V1Config()
    M = {name: _mk(cfg, dem=(name == "C3_local_dem" and dem)) for name, cfg in CANDIDATES.items()
         if dem or name != "C3_local_dem"}
    if include_ablations:
        c2 = CANDIDATES["C2_local_image"]
        M.update({
            "C2/no-exposure": _mk(variant(c2, exposure=False)),
            "C2/no-local(=C1)": _mk(variant(c2, local=False)),
            "C2/no-chroma-cue": _mk(variant(c2, chroma_tau=1e6)),
            "C2/+DCT-detail": _mk(variant(c2, detail=True)),
            "C2/per-band": _mk(variant(c2, shared_gain=False)),
            "C2/fixed-exposure-0.55": _mk(variant(c2, exposure_mode="mean_tau")),
        })
        if dem:
            c3 = CANDIDATES["C3_local_dem"]
            M.update({"C3/no-trust": _mk(variant(c3, rho0=-2.0, rho1=-1.99), dem=True),
                      "C3/no-ensemble": _mk(variant(c3, sun_ensemble=((0.0, 0.0),)), dem=True),
                      "C3/no-shift-search": _mk(variant(c3, dem_shift_search_px=0), dem=True)})
    return M
