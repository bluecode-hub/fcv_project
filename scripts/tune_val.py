"""Tune TASC-Gamma on the D2 *validation* split only (test split is never touched).

Score = mean PSNR on validation pairs (ties broken by shadow MAE).
Writes results/tuning_val.csv and prints the best configuration.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tasc.io_utils import load_tile  # noqa: E402
from tasc.method import TASCGamma  # noqa: E402
from tasc.metrics import psnr, _mean  # noqa: E402
from tasc.io_utils import luminance  # noqa: E402

GRID = dict(tau=[0.50, 0.55], beta=[0.3, 0.6], block_px=[16, 32], gamma_min_shadow=[0.15, 0.25, 0.40],
            k_max=[1.0, 1.2])


def main(data="data/D2_synth", out="results"):
    Path(out).mkdir(exist_ok=True)
    idx = [m for m in json.load(open(Path(data) / "index.json")) if m["split"] == "val"]
    tiles = [load_tile(Path(data) / f"{m['name']}.npz") for m in idx]
    rows = []
    keys = list(GRID)
    for vals in itertools.product(*GRID.values()):
        cfg = dict(zip(keys, vals))
        f = TASCGamma(**cfg, detail=cfg["k_max"] > 1.0)
        ps, sh, dm = [], [], []
        for t in tiles:
            o = f(t["bands"], t["dem"], t["dx"], t["meta"]["sun_az"], t["meta"]["sun_el"])
            ps.append(psnr(o, t["gt"]))
            err = np.abs(luminance(o) - luminance(t["gt"]))
            sh.append(_mean(err, t["mask_shadow"]))
            dm.append(_mean(err, t["mask_dark_material"]))
        rows.append(dict(cfg, psnr=np.mean(ps), mae_shadow=np.nanmean(sh), mae_darkmat=np.nanmean(dm)))
    df = pd.DataFrame(rows).sort_values(["psnr", "mae_shadow"], ascending=[False, True])
    df.to_csv(Path(out) / "tuning_val.csv", index=False)
    print(df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
