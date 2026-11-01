"""Storage layout. All dataset bytes live on the external drive; refuse to run if it is not mounted."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

DEFAULT_MOUNT = "/run/media/ayaan/New Volume"
MOUNT = Path(os.environ.get("TASC_DRIVE", DEFAULT_MOUNT))
ROOT = Path(os.environ.get("TASC_ROOT", MOUNT / "TASC_Research"))
REPO = Path(__file__).resolve().parents[2]
RESEARCH = REPO / "research"

SUBDIRS = ["datasets/landsat_original", "datasets/isaid_dark", "datasets/darkrs", "datasets/aid",
           "datasets/sentinel2", "datasets/copernicus_dem", "datasets/exdark", "datasets/synthetic",
           "cache", "checkpoints", "experiment_outputs", "manifests", "logs"]


class DriveError(RuntimeError):
    pass


def check_drive(min_free_gb: float = 5.0, create: bool = True) -> dict:
    """Verify the external drive is mounted and writable (never formats or repairs anything)."""
    if not os.path.ismount(MOUNT):
        raise DriveError(f"{MOUNT} is not a mount point; refusing to write datasets to the system disk")
    if create:
        for s in SUBDIRS:
            (ROOT / s).mkdir(parents=True, exist_ok=True)
    probe = ROOT / ".write_probe"
    try:
        probe.write_text("ok")
        probe.unlink()
    except OSError as e:
        raise DriveError(f"{ROOT} is not writable: {e}") from e
    free = shutil.disk_usage(MOUNT).free / 1e9
    if free < min_free_gb:
        raise DriveError(f"only {free:.1f} GB free on {MOUNT}")
    return dict(mount=str(MOUNT), root=str(ROOT), free_gb=round(free, 1))


def ds(name: str) -> Path:
    return ROOT / "datasets" / name


def out_dir(name: str) -> Path:
    p = ROOT / "experiment_outputs" / name
    p.mkdir(parents=True, exist_ok=True)
    return p
