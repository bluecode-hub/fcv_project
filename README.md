# TASC-Gamma

**Terrain-Aware, Spectrally Consistent block-adaptive gamma correction for non-uniformly illuminated multispectral satellite imagery.**
Training-free; NumPy/OpenCV only.

Team: Mahek Gupta, Mohammed Ayaan Sheik, Nikita Bhonsale (CSE-AI/ML, Section B).

## Quick start

```bash
pip install -r requirements.txt
python scripts/download_data.py      # only needed if data/raw is empty (≈27 MB)
python scripts/prepare_dataset.py    # builds D1 (real tiles) and D2 (synthetic pairs)
python scripts/tune_val.py           # optional: re-tune on the D2 validation split
python scripts/run_benchmark.py      # all methods, all metrics -> results/
python scripts/make_figures.py       # figures -> results/
```

Use the method on your own data:

```python
from tasc.method import TASCGamma
out = TASCGamma()(bands, dem, dx, sun_az, sun_el)   # bands: [H, W, K] in [0, 1], order B, G, R, NIR, ...
out = TASCGamma()(bands)                             # no DEM -> image-only mode
```

`dx` is the ground pixel size in metres (scalar or per-row array). Sun angles come from scene metadata; for composites without metadata see `tasc/terrain.py` (`estimate_sun_azimuth`, `sun_elevation_from_overpass`).

## Dataset

**Source scene.** Landsat 7 TOA 5-year composite (1999–2003), bands B1–B4 (blue, green, red, NIR), 8-bit, 2127 × 1564 px at 180 m (Web Mercator), over the Sierra Nevada, California (36.6–38.6° N, 117.3–120.8° W). It is paired with SRTM 90 m elevation over the same extent (0–4314 m). Both files come from the public [opengeos/data](https://github.com/opengeos/data) repository (`raster/landsat.tif`, `raster/srtm90.tif`).

The scene is dark and low-contrast, and it contains all three cases the method must separate:

- **Terrain shadow:** east and west faces of the Sierra.
- **Intrinsically dark lit surfaces:** Mono Lake, reservoirs, forest.
- **Bright surfaces to protect:** snow, granite, playas.

**Sun angles.** A composite has no acquisition time.
- **Azimuth** is estimated from the image: high-pass log-luminance is correlated with high-pass log-hillshade, giving **140°**.
- **Elevation** comes from Landsat 7's ~10:00 local overpass geometry at that azimuth and latitude, giving **43.1°**. Elevation cannot be identified from the image itself, since correlation keeps rising as elevation drops.

| Set | What | Size | Used for |
|---|---|---|---|
| `data/D1_real/` | 256 × 256 real tiles + co-registered DEM, ground pixel size, sun angles | 44 tiles (11 mountainous, 8 flat) | No-reference and region-level evaluation |
| `data/D2_synth/` | Flat, well-exposed tiles relit with a physically shaped illumination field: DEM hillshade + cast shadow from a mountain tile at a random sun, 0–2 cloud-shadow blobs, under-exposure 0.35–0.60, Poisson–Gaussian noise, 8-bit quantisation. Stores ground truth, the true illumination, the DEM and exact masks (shadow, lit, dark material, cloud shadow). | 80 pairs: 20 validation / 60 test, split by source tile | Full-reference and region-level evaluation |
| `data/raw/` | Original GeoTIFFs | 2 files | Full-scene run |

Each `.npz` tile holds `bands`, `dem`, `dx`, `valid`, `meta`; D2 tiles also hold `gt`, `illum` and the `mask_*` arrays. Load them with `tasc.io_utils.load_tile`. JPEG previews are in each `preview/` folder.

## Method (`tasc/method.py`)

All steps run on luminance Y. The bands are touched once, by a shared gain map.

| Step | Contribution | What it does |
|---|---|---|
| 0 | – | Global exposure gamma from the image mean |
| 1 | C1 | Block gamma from 16 px block means, capped at 1 (well-lit blocks are never brightened) |
| 2 | C2 | Shadow likelihood S from DEM hillshade + cast shadow. Enhancement weight w = β + (1−β)·S, so dark-but-lit pixels (water, forest) get only β of the lift. In shadow, gamma is re-estimated from the local mean with a lower floor. |
| 3 | C1 | Block values interpolated to pixels, then a guided filter: a seam-free γ(x) |
| 4 | C4 | Global-DCT low-pass gives a base layer. Detail = Y − base, boosted by k(x), with smaller k where the input was dark (noise). |
| 5 | C3 | Gain G = Y_out / Y with a soft highlight knee, applied identically to every band, so NDVI, NDWI and all band ratios are unchanged by construction |

Ablation variants (A0–A5) are defined in `ABLATIONS` at the bottom of `method.py`.

Tuned on the D2 validation split only (`scripts/tune_val.py`): τ = 0.55, β = 0.3, 16 px blocks. k_max = 1.2 is kept on purpose: the validation PSNR prefers no detail boost, as sharpening always costs PSNR against a ground truth, and its benefit is measured with sharpness and NR metrics instead.

## Baselines (`tasc/baselines.py`)

HE, CLAHE, AGC (Rahman 2016), AGCWD (Huang 2013), 2-D gamma with a guided-filter illumination map, global gamma + DCT (Kansal & Tripathi-style), and Zero-DCE (pretrained weights, run in NumPy via `tasc/zerodce.py`).

Classical baselines run per band, the usual practice. `AGCWD+shared` and `CLAHE+shared` run the same curves through TASC-Gamma's shared gain, which isolates the effect of C3.

All baselines are re-implementations from the papers except Zero-DCE, which uses the authors' weights.

## Metrics (`tasc/metrics.py`)

- **Full-reference (D2):** PSNR, SSIM, AMBE.
- **No-reference:** entropy, EME, average gradient, BRISQUE (OpenCV, LIVE model), NIQE. NIQE uses scikit-video's pristine model; it is computed on the full scene only, because 256 px tiles give too few 96 px patches.
- **Region-level:**
  - D2: error in shadow, lit, dark-material and cloud-shadow masks; over-shoot and clipping in lit areas.
  - D1: shadow lift vs dark-material lift and their ratio; clipping in bright areas.
- **Spectral:** NDVI and NDWI MAE, spectral angle (SAM).
- **Artifacts:** block-seam score (1.0 = no new seams).
- **Speed:** ms per megapixel.
- **Statistics:** paired Wilcoxon tests vs TASC-Gamma (`results/wilcoxon.csv`).

## Results

All numbers below come from `results/*.csv` (produced by `scripts/run_benchmark.py`). ↑ higher is better, ↓ lower is better.

### D2 — synthetic, 60 test pairs (ground truth known)

| Method | PSNR ↑ | SSIM ↑ | MAE shadow ↓ | MAE dark material ↓ | MAE cloud shadow ↓ | Over-shoot lit ↓ | Clipped lit ↓ | NDVI MAE vs GT ↓ | ms/MP |
|---|---|---|---|---|---|---|---|---|---|
| Input | 7.77 | 0.361 | 0.468 | 0.196 | 0.420 | 0.000 | 0.000 | 0.018 | – |
| HE | 9.05 | 0.290 | 0.486 | 0.116 | 0.375 | 0.167 | 0.005 | 0.284 | 15 |
| CLAHE | 9.69 | 0.378 | 0.446 | 0.097 | 0.305 | 0.016 | 0.000 | 0.141 | 30 |
| AGC | 10.71 | 0.384 | 0.464 | 0.102 | 0.333 | 0.104 | 0.000 | 0.227 | 44 |
| AGCWD | 11.24 | 0.352 | 0.452 | 0.078 | 0.344 | 0.106 | 0.001 | 0.096 | 35 |
| 2D-gamma | 7.75 | 0.361 | 0.440 | 0.194 | 0.350 | 0.000 | 0.000 | 0.055 | 133 |
| GlobalGamma+DCT | 14.80 | 0.504 | 0.210 | 0.138 | 0.113 | 0.077 | 0.000 | 0.163 | 61 |
| Zero-DCE | 16.89 | 0.490 | 0.297 | 0.088 | 0.133 | 0.043 | 0.081 | 0.041 | 41918 |
| **TASC-Gamma** | 21.65 | 0.644 | 0.130 | 0.029 | 0.094 | 0.007 | 0.000 | 0.018 | 436 |

### Ablations (D2 test split; seam score from D1)

| Method | PSNR ↑ | MAE shadow ↓ | MAE dark material ↓ | MAE cloud shadow ↓ | NDVI MAE ↓ | Seam score on D1 (1 = none) |
|---|---|---|---|---|---|---|
| A0_global_gamma_dct | 20.27 | 0.209 | 0.029 | 0.112 | 0.018 | 0.991 |
| A1_hard_blocks | 21.60 | 0.134 | 0.032 | 0.058 | 0.018 | 1.185 |
| A2_smooth_field | 21.61 | 0.139 | 0.032 | 0.059 | 0.018 | 0.988 |
| A4_no_dem | 21.43 | 0.148 | 0.031 | 0.059 | 0.018 | 0.989 |
| A3_plus_dem | 21.77 | 0.124 | 0.029 | 0.094 | 0.018 | 0.990 |
| **TASC-Gamma** | 21.65 | 0.130 | 0.029 | 0.094 | 0.018 | 0.991 |
| A5_full_per_band | 15.25 | 0.131 | 0.126 | 0.095 | 0.162 | 0.995 |
| AGCWD+shared | 12.53 | 0.453 | 0.049 | 0.346 | 0.018 | 0.999 |
| CLAHE+shared | 10.90 | 0.449 | 0.094 | 0.307 | 0.018 | 0.993 |

### Paired tests (D2)

| Metric | TASC-Gamma vs | TASC better on | p (Wilcoxon) |
|---|---|---|---|
| psnr | A0_global_gamma_dct | 87% of 60 pairs | 3.1e-08 |
| psnr | A4_no_dem | 55% of 60 pairs | 1.6e-01 |
| psnr | GlobalGamma+DCT | 100% of 60 pairs | 1.6e-11 |
| psnr | Zero-DCE | 100% of 60 pairs | 1.6e-11 |
| mae_shadow | A0_global_gamma_dct | 100% of 60 pairs | 1.6e-11 |
| mae_shadow | A4_no_dem | 73% of 60 pairs | 2.0e-04 |
| mae_shadow | GlobalGamma+DCT | 100% of 60 pairs | 1.6e-11 |
| mae_shadow | Zero-DCE | 100% of 60 pairs | 1.6e-11 |

### Full real scene (2127 × 1564)

| Method | Entropy | Shadow entropy | Shadow lift | Dark-material / shadow lift ↓ | Bright clipped ↓ | NDVI MAE ↓ | SAM° ↓ | NIQE ↓ | BRISQUE ↓ | ms/MP |
|---|---|---|---|---|---|---|---|---|---|---|
| Input | 5.75 | 5.35 | 0.000 | – | 0.000 | 0.000 | 0.26 | 9.29 | 8.2 | – |
| HE | 7.92 | 7.57 | 0.236 | 0.382 | 0.724 | 0.289 | 15.95 | 9.32 | 21.2 | 20 |
| CLAHE | 6.75 | 6.35 | 0.059 | 0.644 | 0.000 | 0.112 | 5.78 | 9.69 | 16.4 | 32 |
| AGC | 7.83 | 7.28 | 0.176 | 0.154 | 0.213 | 0.248 | 13.77 | 9.45 | 20.0 | 60 |
| AGCWD | 7.56 | 6.89 | 0.128 | 0.304 | 0.120 | 0.130 | 7.53 | 9.64 | 17.8 | 36 |
| 2D-gamma | 4.96 | 5.31 | 0.008 | 7.298 | 0.000 | 0.178 | 9.77 | 9.45 | 9.0 | 123 |
| GlobalGamma+DCT | 6.15 | 6.05 | 0.405 | 0.975 | 0.000 | 0.186 | 11.91 | 9.67 | 13.3 | 151 |
| Zero-DCE | 6.32 | 6.39 | 0.279 | 1.047 | 0.224 | 0.031 | 2.31 | 9.92 | 19.1 | 48115 |
| **TASC-Gamma** | 6.41 | 6.57 | 0.357 | 0.736 | 0.000 | 0.000 | 0.14 | 9.69 | 13.7 | 654 |

Zero-DCE runtime is NumPy on CPU, and would be far faster in PyTorch on a GPU. HE and AGC show low ratios only because they clip 72% and 21% of bright pixels. "Dark-material / shadow lift" is the luminance lift on lit water and forest divided by the lift in terrain shadow (lower = shadows get more of the brightening).

### What the evidence supports

- **C1 seam-free field — supported.** Hard blocks leave visible seams: seam score 1.18 on real tiles. The smoothed field removes them (0.99) at no cost in PSNR.
- **C3 shared gain — strongly supported.**
  - TASC-Gamma's NDVI and NDWI error vs the input is 0 on real data.
  - Every per-band method distorts NDVI: HE 0.29, AGC 0.25, GlobalGamma+DCT 0.19, AGCWD 0.13, Zero-DCE 0.03.
  - The same gamma field applied per band (A5) loses 6.4 dB PSNR (15.3 vs 21.6) and raises NDVI error from 0.018 to 0.16.
  - The shared gain alone also lifts AGCWD by 1.3 dB.
- **Overall quality — supported on D2.** Best PSNR and SSIM of all full methods, lowest shadow error, no clipping in lit areas. That is +1.4 dB over the global-gamma + DCT ablation and +4.8 dB over Zero-DCE.
- **C2 terrain prior — partly supported.**
  - On D2 the DEM cuts shadow error by 12% (0.130 vs 0.148; better on 73% of pairs, p = 2e-4) and dark-material error by 6% (0.029 vs 0.031). Its PSNR gain over the no-DEM variant is not significant (p = 0.16).
  - It makes cloud shadows worse (0.094 vs 0.059), because clouds are not in a DEM.
  - On the real scene it does **not** change the dark-material/shadow ratio (0.74 with DEM vs 0.72 without). Most of the brightening comes from the global exposure step (step 0), which the DEM does not steer.
- **C4 detail boost — trade-off.** It costs 0.12 dB PSNR (A3 vs full) and raises average gradient slightly. No-reference metrics do not reward it at 180 m.
- **No-reference metrics favour the dark input** (lowest NIQE and BRISQUE), because brightening reveals noise. Report them, but do not lean on them.

### Next steps that matter for the paper

1. Let the DEM steer the exposure step too. For example, apply global exposure as a linear gain and use gamma only for the terrain-shadow residual, so lit dark materials are no longer lifted non-linearly. This is the change most likely to make C2 hold on real data.
2. Add a cloud-shadow mask (Sentinel-2 SCL) to S.
3. Re-run on Sentinel-2 L2A at 10 m with Copernicus DEM GLO-30 and real sun angles from metadata.

**Haze.** On TOA data the shared gain keeps the blue haze ratio, so shadows look blue. `TASCGamma(dark_object_subtraction=True)` removes 60% of each band's dark-object offset first; see `results/fig_haze_dos.jpg`. It is off in the benchmark so all methods see the same input.


## Limitations

- **Cloud shadows are not in a DEM.** With the DEM prior on, cloud shadows only get the β share of the lift, so the image-only variant recovers them better. The next step is adding a cloud-shadow mask (e.g. the Sentinel-2 SCL layer) to S.
- **Coarse data.** The scene is 8-bit at 180 m with a 90 m DEM, so small shadows and fine registration errors are not resolved. Run the same code on Sentinel-2 L2A (10 m) with Copernicus DEM GLO-30 for the paper.
- **No LPIPS.** LPIPS and the PyTorch IQA models were not used, because PyTorch was unavailable in the build environment. Add them with `pyiqa` if you have PyTorch.
- **Comparability of NR scores.** NIQE uses scikit-video's model, so absolute values are not comparable with MATLAB NIQE numbers in other papers; use it for ranking only.
