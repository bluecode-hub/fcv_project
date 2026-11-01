"""Dataset readers. Every reader yields sample dicts in the v0 band convention (B, G, R) float32 in [0, 1]."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from . import paths
from .degrade import degrade

IMG_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}


def read_bgr(path) -> np.ndarray:
    im = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if im is None:
        raise IOError(path)
    return im.astype(np.float32) / 255.0


def _h(s: str, seed: int) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{s}".encode()).digest()[:8], "little")


# ----------------------------------------------------------------- AID
def build_aid_manifest(per_class=10, head_per_class=30, val_fraction=0.3, seed=20261101) -> dict:
    """Class-balanced subset from the download order (same seeded shuffle as fetch_aid.py).
    first `per_class` images of each class -> evaluation pool (split val/test by source image);
    next `head_per_class` -> clean training set of the downstream linear head (E7)."""
    import random
    root = paths.ds("aid")
    listing = json.load(open(root / "listing.json"))
    rng = random.Random(seed)
    ev, head = [], []
    for c in sorted(listing):
        order = [p for p, _, _ in rng.sample(listing[c], len(listing[c]))]
        have = [p for p in order if (root / "images" / c / Path(p).name).exists()]
        ev += [f"{c}/{Path(p).name}" for p in have[:per_class]]
        head += [f"{c}/{Path(p).name}" for p in have[per_class:per_class + head_per_class]]
    ev.sort(key=lambda k: _h("split|" + k, seed))
    n_val = int(round(len(ev) * val_fraction))
    split = {k: ("val" if i < n_val else "test") for i, k in enumerate(ev)}
    return dict(dataset="AID", seed=seed, per_class=per_class, n=len(ev), split=split, head_train=sorted(head),
                classes=sorted({k.split("/")[0] for k in ev}))


def aid_samples(manifest, split, degradations, max_side=None):
    root = paths.ds("aid") / "images"
    for k, sp in sorted(manifest["split"].items()):
        if sp != split:
            continue
        gt = read_bgr(root / k)
        if max_side and max(gt.shape[:2]) > max_side:
            s = max_side / max(gt.shape[:2])
            gt = cv2.resize(gt, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        for d in degradations:
            yield dict(name=f"{k}|{d}", source=k, degradation=d, group=k.split("/")[0],
                       bands=degrade(gt, d, k), gt=gt)


# ----------------------------------------------------------------- unpaired folders
def folder_samples(root, max_images=None, max_side=1024, seed=0):
    files = sorted(f for f in Path(root).rglob("*") if f.suffix.lower() in IMG_EXT)
    files.sort(key=lambda f: _h(str(f.relative_to(root)), seed))
    for f in files[:max_images]:
        im = read_bgr(f)
        if max(im.shape[:2]) > max_side:
            s = max_side / max(im.shape[:2])
            im = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        yield dict(name=str(f.relative_to(root)), source=str(f.relative_to(root)), bands=im)


# ----------------------------------------------------------------- Landsat D2 (v0)
def d2_samples(split="test"):
    from tasc.io_utils import load_tile
    root = paths.ds("landsat_original") / "D2_synth"
    for m in json.load(open(root / "index.json")):
        if m["split"] != split:
            continue
        t = load_tile(root / f"{m['name']}.npz")
        yield dict(name=m["name"], bands=t["bands"], gt=t["gt"], dem=t["dem"], dx=t["dx"],
                   sun_az=t["meta"]["sun_az"], sun_el=t["meta"]["sun_el"], source=m.get("source", m["name"]),
                   **{k: v for k, v in t.items() if k.startswith("mask_")})
