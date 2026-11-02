# Dataset audit

All datasets live on the external drive `/run/media/ayaan/New Volume/TASC_Research/datasets/` (never in Git). Checksums: `dataset_manifests/archives_checksums.json`; sizes: `dataset_manifests/dataset_sizes.json`; per-scene Sentinel-2 provenance: `dataset_manifests/sentinel2_scenes.json`; AID split: `dataset_manifests/aid_subset.json`.

| Dataset | Used as | Items used | On-drive size | Provenance / integrity | Licence / terms | Caveats |
|---|---|---|---|---|---|---|
| Landsat D1/D2 (existing TASC-v0 data) | E1 reproduction, E2 controlled benchmark | D2: 60 test pairs (28 methods) | 0.13 GB | Rebuilt on the drive by `scripts/prepare_landsat.py`; v0 benchmark reproduced (max abs. difference 0.0075 on BRISQUE, <=2e-6 elsewhere) | USGS Landsat (public domain) | D2 darkening/shadows are synthetic and generated from the same DEM that TASC-DEM uses: the DEM benefit is partly built in |
| Sentinel-2 L2A + Copernicus GLO-30 DEM | E3 terrain benchmark | 24 acquisitions, 6 regions x 4 dates, 1536 px windows, 512 px tiles (216 tiles analysed incl. all methods) | 0.42 + 0.33 GB | Earth Search STAC (`sentinel-2-l2a`, `cop-dem-glo-30`), public S3; real sun azimuth/elevation from STAC metadata | Copernicus open licence | No ground-truth illumination; terrain-shadow masks are DEM-derived proxies; SCL is not ground truth; validity from SCL classes 0/1 only; `scl_valid_frac` stored in the files from the first fetch is wrong and is ignored |
| AID (`blanchon/AID` on Hugging Face) | E4 synthetic low-light with references; E7 | 1200 files sha-verified: 300 eval images (210 test / 90 val, 30 classes) + 900 disjoint `head_train` images for the linear probe | 0.33 GB | Hugging Face LFS sha256 verified; disjointness asserted | Academic use (HF licence field "unknown") | Low-light is synthetically generated (three seeded degradations), not real |
| iSAID-dark | E5 | 66 validation pairs (512x512) + 24 high-pixel scenes x 3 darkness levels (15/20/30) = 138 evaluation units | 4.8 GB (4.26 GB archive; 3755 train pairs not extracted) | Archive sha256 `da8d4749...`; folder `iSAID2`; obtained from the Google Drive link in the DFFN README | iSAID/DOTA: non-commercial | Low-light is synthetic darkening. Version could not be verified against a published release number; it is the data distributed with DFFN, not conflated with iSAID-dark2. 72 of 138 units are three darkness levels of 24 scenes (not independent) |
| DarkRS | E6 (no-reference) | 86 real night drone images | 0.07 GB | Archive sha256 `5b3a7801...` | none stated | No references, so no PSNR/SSIM |
| ExDark | E6 (optional, no-reference) | 400 of 7363 images (seeded sample) | 3.0 GB | Zip sha256 `2d21a1ed...` | Non-commercial academic use, aggregate metrics only, no redistribution | No image from ExDark is committed to Git |
| Copernicus DEM | with Sentinel-2 | 24 DEM windows | (see above) | STAC | Copernicus open licence | 30 m DEM resampled to 10 m |

## Exclusions and rejections
* An earlier Sentinel-2 selection with swath-edge/no-data windows and a window outside the tile was rejected and quarantined (`datasets/_rejected_low_coverage_v1/`); selection then used a footprint gate, a coarse overview check, a snow penalty and >=20 days spacing.
* iSAID-dark training pairs (3755) were not extracted or used (TASC is training-free).
* Only a seeded 400-image subset of ExDark was evaluated (cost).
* Held-out regions (Norway Jotunheimen, New Zealand Southern Alps) were fixed a priori in `protocols/sentinel2_regions.yaml` before any tuning or analysis.

## Models/code fetched but not used
* DFFN (`iijjlk/DFFN`, weights `model_best_isaid.pt`, sha256 `92085da6...`): downloaded and checksummed, **not executed** (the execution of downloaded third-party code was blocked by the sandbox permission policy and was not worked around). DFFN is reported as not evaluated. The DFFN repository carries no licence file.
