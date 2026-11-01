"""Integrity tests: frozen v0 untouched, adapter equivalence, degradation determinism, store resume."""
import hashlib
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from research.trs import adapter, degrade  # noqa: E402
from research.trs.store import Store  # noqa: E402
from tasc.method import TASCGamma, shadow_likelihood  # noqa: E402


def test_v0_unchanged_vs_tag():
    out = subprocess.run(["git", "diff", "--stat", "TASC-v0", "--", "tasc/*.py"], cwd=REPO, capture_output=True, text=True)
    assert out.stdout.strip() == "", f"tasc/ differs from TASC-v0:\n{out.stdout}"


def _rng_scene(n=96, k=4, seed=0):
    r = np.random.default_rng(seed)
    b = (r.random((n, n, k)).astype(np.float32) * 0.3 + 0.02)
    dem = (np.cumsum(r.normal(0, 3, (n, n)), 0) + np.cumsum(r.normal(0, 3, (n, n)), 1)).astype(np.float32)
    return b, dem


def test_adapter_fourband_identical_to_v0():
    b, dem = _rng_scene()
    ref = TASCGamma()(b, dem, 10.0, 140.0, 35.0)
    # adapter with S computed exactly like v0 must reproduce v0 output bit-for-bit
    S = shadow_likelihood(dem, 10.0, 140.0, 35.0, True, 2.0)
    out = adapter.run_tasc(b, {}, S=S)
    assert np.array_equal(ref, out)


def test_context_shadow_equals_v0_without_margin():
    b, dem = _rng_scene()
    S0 = shadow_likelihood(dem, 10.0, 140.0, 35.0, True, 2.0)
    full = adapter.shadow_field(dem, 10.0, 140.0, 35.0, max_steps=200)
    S1 = adapter.crop_blur(full, 0, 0, *dem.shape)
    assert np.allclose(S0, S1, atol=1e-5)


def test_rgb_runs_through_v0_and_is_gain_shared():
    r = np.random.default_rng(1)
    x = (r.random((64, 64, 3)) * 0.2).astype(np.float32)
    y = adapter.run_tasc(x, dict(use_dem=False))
    ratio_in = x[..., 0] / (x[..., 2] + 1e-6)
    ratio_out = y[..., 0] / (y[..., 2] + 1e-6)
    m = (x.min(-1) > 0.01) & (y.max(-1) < 0.97)
    assert np.allclose(ratio_in[m], ratio_out[m], rtol=2e-3)


def test_degradation_deterministic():
    x = np.random.default_rng(3).random((64, 64, 3)).astype(np.float32)
    for m in degrade.MODELS:
        assert np.array_equal(degrade.degrade(x, m, "a/b.jpg"), degrade.degrade(x, m, "a/b.jpg"))
    assert not np.array_equal(degrade.degrade(x, "uniform", "a"), degrade.degrade(x, "uniform", "b"))


def test_store_resume(tmp_path):
    s = Store(tmp_path / "r.jsonl")
    s.add(sample="a", method="m", v=1.0)
    s2 = Store(tmp_path / "r.jsonl")
    assert s2.has("a", "m") and not s2.has("a", "n")
    with open(tmp_path / "r.jsonl", "a") as f:
        f.write('{"sample": "b", "meth')           # simulated crash mid-write
    assert not Store(tmp_path / "r.jsonl").has("b", "m")
