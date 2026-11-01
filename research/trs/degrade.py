"""Deterministic synthetic low-light degradations for RGB aerial images (E4).

Each image gets a seed derived from its relative path, so every run reproduces the same
degraded input. Models operate in linear-ish [0,1] display space and end with 8-bit quantisation.
  uniform    : global under-exposure (gamma + gain) + Poisson-Gaussian noise
  nonuniform : smooth multiplicative illumination field (gradients + soft shadow blobs) + noise
  severe     : strong under-exposure with heavier noise
"""
from __future__ import annotations

import hashlib

import cv2
import numpy as np

MODELS = ("uniform", "nonuniform", "severe")


def seed_for(key: str, model: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{key}|{model}".encode()).digest()[:4], "little")


def _field(rng, h, w):
    f = np.ones((h, w), np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ang = rng.uniform(0, 2 * np.pi)
    grad = (np.cos(ang) * (xx / w - .5) + np.sin(ang) * (yy / h - .5))
    f *= 1.0 + rng.uniform(0.4, 0.9) * grad
    for _ in range(rng.integers(1, 4)):
        cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        sx, sy = rng.uniform(.08, .3) * w, rng.uniform(.08, .3) * h
        f *= 1.0 - rng.uniform(.4, .85) * np.exp(-(((xx - cx) / sx) ** 2 + ((yy - cy) / sy) ** 2))
    return np.clip(f, 0.05, 1.5)


def degrade(img01, model, key):
    """img01: float32 [H,W,3] in [0,1] (any channel order). Returns degraded float32 on the 8-bit grid."""
    rng = np.random.default_rng(seed_for(key, model))
    h, w = img01.shape[:2]
    x = np.clip(img01, 0, 1).astype(np.float64)
    if model == "uniform":
        x = rng.uniform(0.35, 0.6) * x ** rng.uniform(1.6, 2.4)
        peak, read = rng.uniform(150, 400), rng.uniform(0.004, 0.01)
    elif model == "nonuniform":
        x = (rng.uniform(.5, .8) * x ** rng.uniform(1.2, 1.8)) * _field(rng, h, w)[..., None]
        peak, read = rng.uniform(150, 400), rng.uniform(0.004, 0.01)
    elif model == "severe":
        x = rng.uniform(0.12, 0.25) * x ** rng.uniform(2.0, 3.0)
        peak, read = rng.uniform(40, 100), rng.uniform(0.01, 0.02)
    else:
        raise ValueError(model)
    x = rng.poisson(np.clip(x, 0, 1) * peak) / peak + rng.normal(0, read, x.shape)
    return (np.clip(np.round(x * 255), 0, 255) / 255).astype(np.float32)
