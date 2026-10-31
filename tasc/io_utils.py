"""Loading scenes and tiles, plus small display helpers."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import cv2

R_EARTH = 6378137.0


def mercator_y_to_lat(y: np.ndarray) -> np.ndarray:
    return np.rad2deg(2.0 * np.arctan(np.exp(y / R_EARTH)) - np.pi / 2.0)


def load_tile(path: str | Path) -> dict:
    """Load one tile saved by scripts/prepare_dataset.py."""
    z = np.load(path, allow_pickle=False)
    d = {k: z[k] for k in z.files}
    if "meta" in d:
        d["meta"] = json.loads(str(d["meta"]))
    return d


def luminance(bands: np.ndarray) -> np.ndarray:
    """Rec.601 luminance from a [H, W, 4] (B, G, R, NIR) array."""
    return 0.299 * bands[..., 2] + 0.587 * bands[..., 1] + 0.114 * bands[..., 0]


def to_rgb8(bands: np.ndarray) -> np.ndarray:
    """True-colour (R, G, B) uint8 image for display / NR-IQA metrics."""
    rgb = np.stack([bands[..., 2], bands[..., 1], bands[..., 0]], -1)
    return np.clip(np.round(rgb * 255.0), 0, 255).astype(np.uint8)


def save_rgb(path: str | Path, bands: np.ndarray, scale: float = 1.0) -> None:
    rgb = to_rgb8(np.clip(bands * scale, 0, 1))
    cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def ndvi(bands: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    nir, red = bands[..., 3].astype(np.float64), bands[..., 2].astype(np.float64)
    return ((nir - red) / (nir + red + eps)).astype(np.float32)


def ndwi(bands: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    g, nir = bands[..., 1].astype(np.float64), bands[..., 3].astype(np.float64)
    return ((g - nir) / (g + nir + eps)).astype(np.float32)
