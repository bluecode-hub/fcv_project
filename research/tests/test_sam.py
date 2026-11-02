"""Regression tests for the corrected spectral-angle metric (research.trs.spectral)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.trs import spectral as SP  # noqa: E402
from tasc import metrics as M0  # noqa: E402


def _rand(n=4000, k=4, seed=0, lo=0.02, hi=0.9):
    return np.random.default_rng(seed).uniform(lo, hi, (n, 1, k)).astype(np.float32)


def test_identical_is_zero():
    a = _rand()
    r = SP.sam_deg_valid(a, a)
    assert r["sam"] < 1e-5 and r["n_used"] == a.shape[0]


def test_positive_scalar_multiple_is_zero_and_gain_invariant():
    a = _rand(hi=0.3)
    for g in (0.5, 1.0, 2.7, 3.0):
        assert SP.sam_deg_valid(a, a * g)["sam"] < 1e-4


def test_known_angles():
    a = np.array([[[1.0, 0, 0, 0]]]); b = np.array([[[0, 1.0, 0, 0]]])
    assert abs(SP.sam_deg_valid(a, b)["sam"] - 90.0) < 1e-9
    c = np.array([[[1.0, 1.0, 0, 0]]])
    assert abs(SP.sam_deg_valid(a, c)["sam"] - 45.0) < 1e-9
    d = np.array([[[1.0, np.sqrt(3.0), 0, 0]]])
    assert abs(SP.sam_deg_valid(a, d)["sam"] - 60.0) < 1e-9
    assert abs(SP.sam_deg_valid(a, -a)["sam"] - 180.0) < 1e-9


def test_zero_and_tiny_vectors_are_excluded_and_counted():
    a = np.zeros((4, 1, 4)); a[1] = 0.5; a[2] = 0.001; a[3] = 0.4
    b = a.copy(); b[3] = 0.8
    r = SP.sam_deg_valid(a, b)
    assert r["n_used"] == 2 and r["n_excl_norm"] == 2 and r["sam"] < 1e-9
    assert np.isnan(SP.sam_deg_valid(np.zeros((3, 1, 4)), np.zeros((3, 1, 4)))["sam"])   # never silently 0


def test_mask_exclusions_recorded():
    a = _rand(100); v = np.zeros((100, 1), bool); v[:60] = True
    r = SP.sam_deg_valid(a, a, v)
    assert r["n_valid_mask"] == 60 and r["n_excl_invalid"] == 40 and r["n_used"] == 60


def test_frozen_metric_defect_is_reproduced():
    """The frozen v0 sam_deg is not 0 for identical input (documented defect); the corrected one is."""
    a = _rand(500, lo=0.0, hi=0.05)
    a[:50] = 0
    assert M0.sam_deg(a, a) > 5.0
    assert SP.sam_deg_valid(a, a)["sam"] < 1e-5


def test_shared_gain_invariance_without_clipping():
    from tasc.method import TASCGamma
    rng = np.random.default_rng(1)
    img = (rng.uniform(0.03, 0.35, (96, 96, 4))).astype(np.float32)
    out = TASCGamma(detail=False)(img)
    r = SP.sam_deg_valid(out, img)
    assert out.max() <= 0.9701 and r["sam"] < 0.05, r     # one gain per pixel (soft knee) -> only float32 rounding


def test_index_and_ratio_metrics_identity_gain_and_zero_pixels():
    a = _rand(2000, hi=0.3); a[:200] = 0.0                       # clipped (zero) pixels
    b = a * 2.5
    for fn in (lambda x, y: SP.nd_index_mae_valid(x, y, 3, 2)[0], lambda x, y: SP.nd_index_mae_valid(x, y, 1, 3)[0],
               lambda x, y: SP.band_ratio_dev_valid(x, y)[0]):
        assert fn(a, a) < 1e-9 and fn(a, b) < 1e-6      # float32 rounding of the scaled copy
    # a method that lifts zero pixels must not be charged for them
    c = a.copy(); c[:200] = 0.3 * np.array([1.0, 0.8, 0.5, 0.2])
    assert SP.nd_index_mae_valid(a, c, 3, 2)[0] < 1e-9 and SP.band_ratio_dev_valid(a, c)[0] < 1e-9
    # but a genuine change of band ratios is detected
    d = a.copy(); d[..., 3] *= 1.5
    assert SP.nd_index_mae_valid(a, d, 3, 2)[0] > 0.01 and SP.band_ratio_dev_valid(a, d)[0] > 0.01
