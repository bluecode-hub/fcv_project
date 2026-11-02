# Results summary (all numbers are measured; source tables in `research/tables/`)

Branch `research/illumination-aware-benchmark-v1`; frozen baseline tag `TASC-v0` = `297a6d7`. All experiment stores completed with **0 failures**.

## Completeness
| Experiment | Units | Methods | Rows | Failures |
|---|---|---|---|---|
| E1 TASC-v0 reproduction | 1,768 rows (original benchmark) | 16 | 1,768 | 0 (max abs diff 0.0075 BRISQUE; <=2e-6 others) |
| E2 Landsat D2 | 60 pairs | 28 | 1,680 | 0 |
| E3 Sentinel-2 + DEM | 24 scenes / 216 tiles / 6 regions | 29 | 6,264 | 0 |
| E4 AID | 210 test images x 3 degradations | 17 | 10,710 | 0 |
| E5 iSAID-dark | 66 val + 72 high-pixel units | 12 | 1,656 | 0 |
| E6a DarkRS | 86 | 12 | 1,032 | 0 |
| E6b ExDark | 400 | 12 | 4,800 | 0 |
| E7 downstream (AID probe) | 210 test images x 3 degradations | 12 variants | 39 accuracy cells | 0 |
| Efficiency | 1 MP image | 12 | 12 | 0 (peak RSS not valid, see limitations) |

## Principal findings
1. **Landsat D2** (synthetic shading, same DEM): TASC-v0 PSNR 21.65 dB / SSIM 0.644 / LPIPS 0.202 / shadow MAE 0.130, best of 9 compared methods on PSNR/LPIPS/MAE; +2.43 dB over global gamma, +4.76 dB over Zero-DCE. DEM vs image-only: +0.22 dB (n.s., p_Holm 0.49) but shadow MAE -0.018 (p_Holm 0.001).
2. **Integrity controls on D2**: beta-only -1.86 dB, flipped DEM -1.20 dB, 2.9 km shift -1.0 dB; azimuth +-15 deg ~ -0.05 dB; elevation -7 deg **+0.80 dB** (PSNR rewards mis-specification); removing the DCT detail step +0.12 dB (not supported); per-band gamma -6.40 dB and NDVI error 0.162.
3. **Sentinel-2** (real sun angles, DEM proxy masks, n = 4 dev + 2 held-out regions): TASC-DEM shadow lift 0.218 vs image-only 0.193 (dev), 0.156 vs 0.105 (held-out); wrong/shifted DEM erase the selectivity gain; equalisation of vegetation in shadow vs lit **not** improved (0.012 vs 0.197 dev; -0.433 vs -0.315 held-out). Spectra preserved (NDVI error <= 0.001, SAM <= input) versus Zero-DCE (NDVI 0.136, SAM 20.2 deg).
4. **AID synthetic low light**: TASC-image PSNR 11.51 dB (+1.19 over input) but -4.15 dB vs global gamma, -4.94 dB vs Zero-DCE; SSIM/LPIPS worse than input. Removing the global exposure step gives 15.56 dB.
5. **iSAID-dark**: TASC-image 9.51 dB, **below the unprocessed input** (11.78) and Zero-DCE (13.38).
6. **Real night images (no reference)**: TASC-image lowest entropy (DarkRS 6.06 vs 6.48 input), lowest EME, BRISQUE worse than input (DarkRS 24.5 vs 18.3; ExDark 29.1 vs 23.9); NIQE equal (DarkRS) or slightly better (ExDark 11.71 vs 12.27).
7. **Downstream (AID linear probe)**: TASC-image accuracy 0.638/0.710/0.343 vs input 0.838/0.857/0.581 (uniform/non-uniform/severe); all differences' CIs exclude 0. Zero-DCE, CLAHE, AGCWD about equal to input.
8. **Efficiency (CPU, 1 MP, single process)**: TASC-image 114 ms/MP; CLAHE 13; HE 21; AGCWD 22; global gamma 51; Zero-DCE ~33,000 ms/MP.

## Not available / not done
SAGC, SAMSIE (no verified code); DFFN (downloaded, not executed); detection/segmentation downstream; GPU runs; DEM-assisted efficiency; per-method peak memory.

Key tables: `tables/d2_summary.csv`, `s2_summary_{dev,heldout,all}.csv`, `aid_summary.csv`, `isaid_summary.csv`, `darkrs_summary.csv`, `exdark_summary.csv`, `downstream_accuracy.csv`, `efficiency.csv`, and `*_vs_*.csv` for paired statistics.
