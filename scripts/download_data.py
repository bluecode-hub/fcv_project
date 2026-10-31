"""Download the raw scene, DEM and Zero-DCE weights (about 27 MB in total).

    python scripts/download_data.py

Sources
  landsat.tif  Landsat 7 TOA 5-year composite (1999-2003), bands B1-B4 (blue, green,
               red, NIR), 8-bit, Sierra Nevada, California; from the opengeos/data
               repository (Google Earth Engine LANDSAT_LE7_TOA_5YEAR export).
  srtm90.tif   SRTM 90 m DEM over the same extent, same repository.
  Epoch99.pth  Zero-DCE pretrained weights, from Li-Chongyi/Zero-DCE.
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ("https://raw.githubusercontent.com/opengeos/data/main/raster/landsat.tif",
     ROOT / "data/raw/landsat.tif", "8e224b47bfe46c8a27183b516f47c50193daad40742b4a0fa224898e11a8bfcb"),
    ("https://raw.githubusercontent.com/opengeos/data/main/raster/srtm90.tif",
     ROOT / "data/raw/srtm90.tif", "4cfc724096b8d4b3395b9a3fea9c5b251ad816d6395a47aa626bff037e18fcd1"),
    ("https://raw.githubusercontent.com/Li-Chongyi/Zero-DCE/master/Zero-DCE_code/snapshots/Epoch99.pth",
     ROOT / "tasc/weights/zerodce_Epoch99.pth", "a4395acb874f320375d9704997cef874eaaaaa26a1777ceb29a92b70f74c3612"),
]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    for url, dst, digest in FILES:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and sha256(dst) == digest:
            print(f"ok      {dst.relative_to(ROOT)}")
            continue
        print(f"fetch   {url}")
        urllib.request.urlretrieve(url, dst)
        if sha256(dst) != digest:
            sys.exit(f"checksum mismatch for {dst} - the upstream file changed")
        print(f"saved   {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
