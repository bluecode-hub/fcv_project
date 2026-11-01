# Experimental protocol (frozen before any new-dataset result was inspected)

Branch: `research/illumination-aware-benchmark-v1`; baseline tag `TASC-v0` = commit `297a6d7` of `main`.
Methodology is TASC-Gamma exactly as in `tasc/` at that commit. `tasc/` is not edited on this branch.

## Fixed method settings (TASC-v0 defaults, no re-tuning)
tau 0.55, gamma_min 0.40, block 16 px, beta 0.30, gamma_min_shadow 0.25, k_max 1.2, DCT cut-off 0.12,
guided filter r=8 eps=1e-3, cast shadow on, shared gain with soft knee 0.85/0.97, DOS off.
Two configurations: **TASC-image** (`use_dem=False`) and **TASC-DEM** (terrain prior from DEM + sun angles).

## Adapter (research/trs/adapter.py)
* RGB images use the v0 band order (B,G,R); v0 code runs unchanged on 3 bands (luminance reads bands 0-2 only).
* The only change for DEM data is *context*: the shadow field is computed on a DEM window with a 256 px margin
  (2.56 km at 10 m) and cropped to the tile, instead of v0's per-tile computation which cuts off shadow
  sources at tile edges. Same Horn slope / Lambert / ray-march / Gaussian code, injected via `S_override`.
* Equivalence tests (research/tests): 4-band v0 output is bit-identical through the adapter;
  context shadow equals v0 shadow when no margin is available.

## Datasets and splits
| Dataset | Use | Split rule |
|---|---|---|
| Landsat D1/D2 (v0) | continuity, GT ablations, geometry robustness | v0 split (D2: 20 val / 60 test by source tile) |
| AID | image-only evaluation, controlled degradations (E4), downstream (E7) | stratified sample, 10 images/class, split by *source image* 30 % val / 70 % test, seed 20261101 |
| iSAID-dark | paired real-GT enhancement | published train/val/test split of the release |
| DarkRS | real low-light, no reference | test set as released; **no PSNR/SSIM** |
| Sentinel-2 L2A + GLO-30 | E2, E3, E5 | region-level: dev = alps_valais, colorado_rockies, atacama_andes, ladakh; held-out = norway_jotunheimen, nz_southern_alps (fixed a priori in `protocols/sentinel2_regions.yaml`) |
| ExDark | optional out-of-domain image-only | all images, aggregate metrics only |

## Statistics
Unit of analysis: AID source image (degradations averaged first), iSAID/DarkRS image, Sentinel-2 *region*
(tiles -> scenes -> region means; 6 regions so inference is limited), D2 source tile. Paired Wilcoxon
signed-rank, Holm correction over the comparisons in each family, 95 % percentile bootstrap CI (10 000
resamples) of the mean paired difference. All completed and failed runs are reported.

## Proxies and circularity
Terrain-shadow masks derive from the same DEM prior the DEM-assisted method uses. They are **proxies**, not
independent annotation. Evaluation therefore (a) classifies material by spectral indices independent of the
DEM, (b) uses a material-matched illumination-equalisation score, (c) compares against controls that use a
wrong or shifted DEM. SCL labels are never treated as ground truth.
