# Results summary (corrected; every number is measured, source tables in `research/tables/`)

Branch `research/illumination-aware-benchmark-v1`; frozen baseline tag `TASC-v0` = `297a6d7`. All experiment stores completed with **0 failures**. This version supersedes the first summary (kept in `research/archive_v1_pre_correction/reports/`); see `scientific_corrections.md`.

## Completeness
| Experiment | Independent units | Methods | Rows | Failures |
|---|---|---|---|---|
| E1 TASC-v0 reproduction | 1,768 rows (original benchmark) | 16 | 1,768 | 0 (max abs diff 0.0075 BRISQUE; <=2e-6 others) |
| E2 Landsat D2 | 6 source crops (60 pairs, one scene) | 28 | 1,680 | 0 |
| E3 Sentinel-2 + DEM | 6 regions (24 scenes, 216 tiles) | 29 | 6,264 | 0 |
| E4 AID | 210 source images (x 3 degradations) | 17 | 10,710 | 0 |
| E5 iSAID-dark | 46 parent images (138 files) | 12 | 1,656 | 0 |
| E6a DarkRS | 86 | 12 | 1,032 | 0 |
| E6b ExDark | 400 | 12 | 4,800 | 0 |
| E7 downstream (AID probe) | 210 test images per degradation | 12 variants | 39 accuracy cells | 0 |
| Efficiency | 1 MP image | 12 | 12 | 0 (peak RSS invalid) |
| Correction pass: spectral metrics | D2 1,680 rows; Sentinel-2 6,264 rows | 28 / 29 | 7,944 | 0 |

## Principal findings
1. **Landsat D2** (6 crops of one scene, synthetic shading from the same DEM): TASC-v0 PSNR 21.65 dB / SSIM 0.644 / LPIPS 0.202 / shadow MAE 0.130, the best non-TASC-variant method including per-band baselines; +2.43 dB over global gamma (CI 1.89-2.87), +4.76 dB over Zero-DCE (3.94-5.51), 6/6 crops, **but p_Holm = 0.84 for every comparison (n = 6)**. DEM vs image-only: +0.22 dB (CI 0.16-0.28), shadow MAE -0.018 (-0.022..-0.013); at the dependent variant level the PSNR CI is -0.02..0.48.
2. **Integrity controls on D2**: beta-only -1.86 dB, flipped DEM -1.20 dB, 2.9 km shift -1.0 dB; azimuth +-15 deg ~ -0.05 dB; elevation -7 deg **+0.80 dB** (PSNR rewards mis-specification); removing the DCT detail step +0.12 dB (not supported); per-band gamma -6.40 dB.
3. **Spectra (corrected metric)**: output-vs-input SAM, NDVI/NDWI error and band-ratio deviation are exactly 0 for all shared-gain methods (equal to the input vs itself; by construction). The earlier "TASC 8.2 deg vs input 8.9 deg" statement is withdrawn (defective metric). Non-shared-gain methods: per-band 7-19 deg, histogram methods 4-13 deg, topographic corrections 2.4-4.4 deg, Zero-DCE 2.1-2.3 deg. On D2, reconstruction SAM vs the clean reference is 1.52 deg for every shared-gain method (inherited from the degraded input), Zero-DCE 3.46 deg.
4. **Sentinel-2** (exploratory; n = 4 dev + 2 held-out regions; DEM-derived masks, circular): TASC-DEM shadow lift 0.218 vs image-only 0.193 (dev), 0.156 vs 0.105 (held-out); wrong/shifted DEM remove the selectivity gain; per-band variants lift more (0.30-0.33) but change spectra; equalisation of vegetation in shadow vs lit **not** improved (0.012 vs 0.197 dev; -0.433 vs -0.315 held-out).
5. **AID synthetic low light**: best baseline = per-band global gamma (17.51 dB, SSIM 0.490, LPIPS 0.555); TASC-image 11.51 dB (+1.19 over input, **-5.99 vs best baseline**, -4.15 vs global gamma, -4.94 vs Zero-DCE); SSIM/LPIPS worse than input. Removing the global exposure step gives 15.56 dB.
6. **iSAID-dark** (46 parents): TASC-image 9.51 dB, **below the input** (11.78; -2.26, CI -3.19..-1.36), Zero-DCE 13.38, best baseline per-band global gamma 14.40.
7. **Real night images (no reference)**: TASC-image entropy 6.06 vs 6.48 input on DarkRS (only 2D-gamma lower), lowest EME on DarkRS, BRISQUE worse than input (DarkRS 24.5 vs 18.3; ExDark 29.1 vs 23.9); NIQE equal (DarkRS) or slightly better (ExDark 11.71 vs 12.27).
8. **Downstream (AID linear probe)**: TASC-image accuracy 0.638/0.710/0.343 vs input 0.838/0.857/0.581 (uniform/non-uniform/severe); CIs exclude 0. Other methods within about +-0.06 of the input.
9. **Efficiency (CPU, 1 MP, single process)**: TASC-image 114 ms/MP; CLAHE 13; HE 21; AGCWD 22; global gamma 51; Zero-DCE ~33,000 ms/MP.

## Not available / not done
SAGC, SAMSIE (no verified code), DFFN (downloaded, not executed); detection/segmentation; GPU runs; DEM-assisted efficiency; per-method peak memory; a compiled IEEEtran PDF (WeasyPrint fallback only).
