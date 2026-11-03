"""TASC-v1 configuration. Defaults = the development-selected setting recorded in research/reports/phase4_dev_selection.md
(until that file exists they are the a-priori values from protocols/phase4_preregistration.md)."""
from __future__ import annotations

from dataclasses import dataclass, asdict, replace


@dataclass
class V1Config:
    # ---- Component 1: adaptive global exposure (highlight-anchored gamma with a mean ceiling)
    exposure: bool = True
    exposure_mode: str = "highlight"   # "highlight" (v1) or "mean_tau" (v0-style fixed-target rule, ablation only)
    tau_fixed: float = 0.55
    exp_q: float = 95.0          # percentile of luminance that is mapped to the white target
    t_white: float = 0.75        # target level of that percentile
    mean_cap: float = 0.50       # the global gamma never makes mean(Y) exceed this
    gamma_min_global: float = 0.35
    # ---- Component 2: shadow-vs-dark-material confidence and local lift
    local: bool = True
    ill_percentile: float = 80.0 # surround "lit level" = this percentile of smoothed luminance in a large window
    ill_window_frac: float = 0.25  # window side as a fraction of the short image side
    sigma_frac: float = 0.006    # smoothing of the luminance used for the evidence (fraction of short side)
    r_hi: float = 0.80           # Ys/L >= r_hi: no darkness evidence
    r_lo: float = 0.35           # Ys/L <= r_lo: full darkness evidence
    chroma_tau: float = 0.30     # log-chromaticity distance (to lit surround) at which material-consistency falls to e^-1
    water_penalty: float = 0.8   # NIR: NDWI-based reduction of confidence for water-like pixels
    target_kappa: float = 0.90   # local target = kappa * surround lit level
    gamma_min_local: float = 0.40
    gf_radius: int = 8
    gf_eps: float = 1e-3
    # ---- Component 3: DEM guidance with trust estimation
    use_dem: bool = True
    dem_shift_search_px: int = 24   # max translation (full-res px) searched when registering the shadow field to the image
    dem_shift_gain: float = 0.05    # accept a shift only if agreement improves by this much
    rho0: float = 0.10              # agreement at which the DEM weight starts
    rho1: float = 0.40              # agreement at which the DEM weight is 1
    sun_ensemble: tuple = ((0.0, 0.0), (8.0, -3.0), (-8.0, 3.0))   # (d_azimuth, d_elevation) perturbations
    prior_sigma: float = 2.0
    gamma_min_shadow: float = 0.30
    # ---- Component 4: DCT detail (OFF by default; ablation only)
    detail: bool = False
    k_max: float = 1.2
    dct_cutoff: float = 0.12
    # ---- Component 5: shared gain
    shared_gain: bool = True
    gain_cap: float = 6.0        # noise guard: maximum luminance gain
    knee: float = 0.85
    top: float = 0.97

    def as_dict(self):
        return asdict(self)


# The three pre-registered candidates (protocols/phase4_preregistration.md)
CANDIDATES = {
    "C1_exposure": V1Config(local=False, use_dem=False),
    "C2_local_image": V1Config(use_dem=False),
    "C3_local_dem": V1Config(),
}

def variant(base: V1Config, **kw) -> V1Config:
    return replace(base, **kw)
