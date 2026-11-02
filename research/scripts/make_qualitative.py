"""Qualitative Sentinel-2 examples (open Copernicus data) -> figures/fig_qual_s2.png.
Only Sentinel-2/Copernicus DEM tiles are rendered: AID, iSAID, DarkRS and ExDark imagery is not redistributed."""
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trs import s2data, experiments as ex  # noqa: E402
from trs.adapter import shadow_field  # noqa: E402

PICK = ["ladakh", "colorado_rockies", "alps_valais", "norway_jotunheimen"]
SHOW = ["Identity", "GlobalGamma", "CLAHE", "TASC-image", "TASC-DEM"]
M = ex.s2_methods()
rows = []
for reg in PICK:
    metas = [m for m in s2data.list_scenes() if m["region"] == reg][:2]   # first two acquisitions per region (cost)
    best = None
    for m in metas:
        sc = s2data.load_scene(m["name"])
        z = np.zeros_like(sc["dem"])
        V = {"S": shadow_field(sc["dem"], m["dx"], m["sun_az"], m["sun_el"], max_steps=400), "_cos_i": z, "_slope": z}
        for s in s2data.tiles(sc, V):
            score = float(s["S"][s["valid"]].mean())
            if best is None or score > best[0]:
                best = (score, s, m["name"])
    rows.append(best)
fig, ax = plt.subplots(len(rows), len(SHOW) + 1, figsize=(2.3 * (len(SHOW) + 1), 2.3 * len(rows)))
for i, (score, s, name) in enumerate(rows):
    rgb = lambda a: np.clip(a[..., [2, 1, 0]], 0, 1) ** (1 / 2.2)   # display gamma only for viewing
    for j, k in enumerate(SHOW):
        out = M[k](s)
        out = out[0] if isinstance(out, tuple) else out
        ax[i, j].imshow(rgb(out)); ax[i, j].axis("off")
        if i == 0: ax[i, j].set_title(k, fontsize=8)
    ax[i, -1].imshow(s["S"], cmap="magma", vmin=0, vmax=1); ax[i, -1].axis("off")
    if i == 0: ax[i, -1].set_title("DEM shadow field S", fontsize=8)
    ax[i, 0].text(4, 20, f"{s['region']}\nsun {s['sun_az']:.0f}/{s['sun_el']:.0f}", color="w", fontsize=6, va="top")
plt.tight_layout()
out = Path(__file__).resolve().parents[1] / "figures" / "fig_qual_s2.png"
plt.savefig(out, dpi=130)
print("wrote", out)
