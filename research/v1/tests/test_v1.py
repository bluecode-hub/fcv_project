import subprocess, sys
from pathlib import Path
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from research.v1 import TASCv1, V1Config, CANDIDATES          # noqa: E402
from research.v1.exposure import exposure_gamma                 # noqa: E402
from research.v1 import terrain_guidance as TG                  # noqa: E402
from research.trs import spectral as SP                         # noqa: E402


def scene(h=96, w=128, k=4, seed=0, lit=0.55, shadow=0.15):
    """Two-material scene (bright field, a different bright field) with a rectangular soft illumination shadow."""
    rng = np.random.default_rng(seed)
    alb = np.zeros((h, w, k), np.float32)
    alb[..., :4] = np.array([0.35, 0.5, 0.45, 0.7][:k]) * lit / 0.5
    alb[:, w // 2:, :] *= np.array([1.0, 0.8, 0.9, 1.1][:k])
    ill = np.ones((h, w), np.float32)
    ill[h // 4:h // 2, w // 8:w // 3] = shadow / lit
    return np.clip(alb * ill[..., None] + rng.normal(0, 0.003, alb.shape), 0, 1).astype(np.float32), ill


@pytest.mark.parametrize("val", [0.0, 0.5, 1.0])
def test_constant_images_finite(val):
    for k in (3, 4):
        o = TASCv1()(np.full((40, 50, k), val, np.float32))
        assert np.isfinite(o).all() and o.min() >= 0 and o.max() <= 1


def test_zero_image_stays_zero():
    assert TASCv1()(np.zeros((32, 32, 4), np.float32)).max() == 0.0


def test_nan_inf_input_sanitised():
    b = np.full((20, 20, 3), 0.2, np.float32); b[0, 0] = np.nan; b[1, 1] = np.inf
    assert np.isfinite(TASCv1()(b)).all()


@pytest.mark.parametrize("hw", [(2, 2), (3, 5), (17, 23), (64, 64), (130, 70)])
def test_sizes_and_boundaries(hw):
    b = np.random.default_rng(1).uniform(0, 0.4, (*hw, 4)).astype(np.float32)
    o = TASCv1()(b)
    assert o.shape == b.shape and np.isfinite(o).all() and o.min() >= 0 and o.max() <= 1


def test_bad_shape():
    with pytest.raises(ValueError):
        TASCv1()(np.zeros((10, 10, 2), np.float32))
    with pytest.raises(AttributeError):
        TASCv1(nonexistent=1)


def test_deterministic():
    b, _ = scene()
    assert np.array_equal(TASCv1()(b), TASCv1()(b))


def test_never_darkens_luminance_much_and_clips():
    b, _ = scene(lit=0.2, shadow=0.05)
    o = TASCv1()(b)
    ratio = o.sum(-1) / np.maximum(b.sum(-1), 1e-6)
    assert ratio.min() >= 1.0 - 1e-4          # gamma<=1 and shared gain >= 1 except at the highlight knee
    assert o.max() <= 1.0


def test_shared_gain_preserves_spectrum_exactly():
    b, _ = scene(lit=0.25, shadow=0.06)
    o = TASCv1()(b)
    s = SP.sam_deg_valid(o, b)
    assert s["sam"] < 1e-3
    nd, n, _ = SP.nd_index_mae_valid(o, b, 3, 2)
    assert nd < 1e-5 and n > 0
    br, _, _ = SP.band_ratio_dev_valid(o, b)
    assert br < 1e-4


def test_per_band_ablation_changes_spectrum():
    b, _ = scene(lit=0.25, shadow=0.06)
    o = TASCv1(shared_gain=False)(b)
    assert SP.sam_deg_valid(o, b)["sam"] > 0.1


def test_exposure_properties():
    rng = np.random.default_rng(0)
    assert exposure_gamma(np.full((50, 50), 0.8)) == 1.0                        # adequate image: no lift
    dark_with_bright = np.clip(rng.uniform(0, 0.1, (80, 80)), 0, 1); dark_with_bright[:24] = 0.9
    assert exposure_gamma(dark_with_bright, q=75) == 1.0                         # dark scene with bright objects
    g = [exposure_gamma(np.full((50, 50), q)) for q in (0.05, 0.1, 0.2, 0.4)]
    assert all(0.35 <= x <= 1.0 for x in g) and g == sorted(g)                   # monotone in q, bounded
    y = np.clip(rng.uniform(0, 0.3, (100, 100)), 1e-4, 1)
    g0 = exposure_gamma(y)
    assert (y ** g0).mean() <= 0.5 + 1e-3


def test_natural_dark_scene_not_lifted_locally():
    """Evenly lit dark material everywhere: no surround is brighter, so local lift must be ~0."""
    b = np.full((96, 128, 4), 0.06, np.float32) * np.array([1.0, 1.1, 0.9, 1.2], np.float32)
    o, m = TASCv1(exposure=False)(b, return_maps=True)
    assert m["C"].max() < 0.05
    assert np.abs(o - b).max() < 0.01


def test_shadow_lifted_more_than_lit():
    b, ill = scene(lit=0.5, shadow=0.12)
    o, m = TASCv1(exposure=False, use_dem=False)(b, return_maps=True)
    sh = ill < 0.5
    lift_sh = (o.mean(-1)[sh] / b.mean(-1)[sh]).mean()
    lift_lit = (o.mean(-1)[~sh][::7] / b.mean(-1)[~sh][::7]).mean()
    assert lift_sh > 1.3 and lift_sh > lift_lit + 0.2


def test_dark_material_with_different_chromaticity_lifted_less_than_shadow():
    h, w = 96, 128
    base = np.tile(np.array([0.4, 0.5, 0.45, 0.6], np.float32), (h, w, 1))
    b = base.copy()
    b[10:40, 10:50] *= 0.25                                    # illumination shadow: chromaticity preserved
    b[55:85, 70:110] = np.array([0.02, 0.10, 0.015, 0.01], np.float32)   # dark, green-ish, low-NIR material (water-like)
    o, m = TASCv1(exposure=False, use_dem=False)(b, return_maps=True)
    assert m["C"][10:40, 10:50].mean() > m["C"][55:85, 70:110].mean() + 0.2


def test_dem_trust_wrong_vs_right():
    b, ill = scene(lit=0.5, shadow=0.1)
    cfg = V1Config(exposure=False)
    S_right = np.clip(1 - ill / 1.0, 0, 1).astype(np.float32)
    ev = __import__("research.v1.shadow_confidence", fromlist=["x"]).image_confidence(b, np.clip(b[..., 0] * 0 + b.mean(-1), 1e-4, 1), cfg)
    _, w_right, _ = TG.register_and_trust(S_right, ev["D"], cfg)
    rng = np.random.default_rng(3)
    S_wrong = np.zeros_like(S_right); S_wrong[60:90, 80:120] = 1.0
    _, w_wrong, _ = TG.register_and_trust(S_wrong, ev["D"], cfg)
    assert w_right > 0.8 and w_wrong < 0.2


def test_dem_shift_is_recovered():
    b, ill = scene(lit=0.5, shadow=0.1)
    cfg = V1Config(exposure=False)
    S = np.clip(1 - ill, 0, 1).astype(np.float32)
    S_shift = np.roll(S, (6, 10), axis=(0, 1))
    ev = __import__("research.v1.shadow_confidence", fromlist=["x"]).image_confidence(b, b.mean(-1), cfg)
    Sr, w, info = TG.register_and_trust(S_shift, ev["D"], cfg)
    assert w > 0.5
    err_before = np.abs(S_shift - S).mean(); err_after = np.abs(Sr - S).mean()
    assert err_after < 0.35 * err_before, (err_before, err_after, info)


def test_wrong_dem_does_not_exceed_image_only_much():
    b, ill = scene(lit=0.5, shadow=0.1)
    S_wrong = np.zeros(b.shape[:2], np.float32); S_wrong[60:90, 80:120] = 1.0
    o_img = TASCv1(exposure=False, use_dem=False)(b)
    o_wrong = TASCv1(exposure=False)(b, S=S_wrong)
    assert np.abs(o_wrong - o_img).mean() < 0.01


def test_rgb_and_rgbnir_both_run():
    b, _ = scene(k=4)
    o4 = TASCv1()(b); o3 = TASCv1()(b[..., :3])
    assert o4.shape[-1] == 4 and o3.shape[-1] == 3


def test_candidates_run():
    b, _ = scene(lit=0.2, shadow=0.05)
    for name, cfg in CANDIDATES.items():
        o = TASCv1(cfg)(b)
        assert np.isfinite(o).all(), name


def test_frozen_v0_unchanged():
    r = subprocess.run(["git", "diff", "--stat", "TASC-v0", "--", "tasc"], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_float64_and_uint_range_inputs():
    b, _ = scene()
    o = TASCv1()(b.astype(np.float64))
    assert o.dtype == np.float32
