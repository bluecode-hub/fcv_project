"""Rebuild the v0 Landsat D1/D2 data on the external drive (v0 scripts unchanged) and link data/ -> drive."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from research.trs import paths  # noqa: E402


def main():
    paths.check_drive(5)
    dst = paths.ds("landsat_original")
    link = REPO / "data"
    if not link.exists():
        os.symlink(dst, link)
    py = sys.executable
    if not (dst / "raw/landsat.tif").exists():
        subprocess.check_call([py, "scripts/download_data.py"], cwd=REPO)
    if not (dst / "D2_synth/index.json").exists():
        subprocess.check_call([py, "scripts/prepare_dataset.py", "--raw", "data/raw", "--out", "data"], cwd=REPO)
    print("landsat ready:", dst)


if __name__ == "__main__":
    main()
