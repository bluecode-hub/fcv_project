# Benchmark-integrity controls

Every control runs through the same frozen v0 code path (adapter injects a different shadow field S or sun angle; `trs/adapter.py`, `trs/experiments.py`). Numbers are means over units; paired differences with 95 % bootstrap CIs are in `tables/*_vs_*.csv`.

## Landsat D2 (60 pairs; reference-based; PSNR dB / MAE in shadow)
| Control | PSNR | MAE shadow | Reading |
|---|---|---|---|
| TASC-v0 (true DEM, true sun) | 21.65 | 0.130 | reference |
| No DEM (image-only) | 21.43 | 0.148 | DEM adds +0.22 dB (CI -0.02..0.48, n.s. after Holm) but lowers shadow MAE by 0.018 (CI 0.009..0.026, p_Holm = 0.001) |
| beta-only (S = 0) | 19.79 | 0.209 | -1.86 dB: the shadow term matters, not just the constant lift |
| Flipped DEM | 20.45 | 0.187 | -1.20 dB: wrong terrain hurts |
| DEM shifted 720 m / 2.9 km | 21.25 / 20.65 | 0.150 / 0.179 | monotone degradation with misregistration |
| Sun azimuth +15 / -15 / +45 deg | 21.59 / 21.58 / 21.23 | 0.132 / 0.133 / 0.149 | small sensitivity to azimuth error |
| Sun elevation +7 / -7 deg | 21.07 / **22.45** | 0.153 / **0.102** | **-7 deg beats the true metadata**: PSNR rewards a larger shadow field on under-exposed images; metric is not a measure of geometric correctness |
| Without DCT detail boost | 21.77 | 0.124 | removing the DCT detail step is slightly *better* on PSNR (+0.12 dB, CI 0.09..0.16) and MAE; LPIPS 0.198 vs 0.202 |
| Global gamma + DCT (A0) | 20.27 | 0.209 | v0 beats A0 by 1.38 dB (CI 1.03..1.74) |
| Per-band gamma (no shared gain) | 15.25 | 0.131 | -6.40 dB; NDVI error 0.162 vs 0.018 (shared gain preserves ratios) |
| Identity, GlobalGamma, Zero-DCE | 7.78, 19.22, 16.89 | 0.468, 0.224, 0.297 | v0 beats all |

## Sentinel-2 (6 regions, 24 scenes; no reference; lift = mean luminance increase in DEM-shadow proxy)
Development regions (n = 4):

| Variant | lift in shadow | dark-lit / shadow lift (lower = more selective) | equalisation gain |
|---|---|---|---|
| TASC-DEM | 0.218 | 0.287 | 0.012 |
| TASC-image | 0.193 | 0.439 | 0.197 |
| beta-only | 0.150 | 0.376 | 0.281 |
| wrong DEM | 0.169 | 0.443 | 0.228 |
| DEM shifted 300 m / 1 km | 0.202 / 0.184 | 0.336 / 0.425 | 0.118 / 0.236 |
| az +15 / -15 | 0.215 / 0.215 | 0.302 / 0.302 | 0.065 / 0.059 |
| el +7 / -7 | 0.202 / 0.231 | 0.298 / 0.302 | 0.059 / 0.036 |
| GlobalGamma | 0.126 | 0.417 | 0.320 |
| Zero-DCE | 0.124 | 0.397 | 0.026 |

* Correct terrain gives the largest shadow lift and the most selective lift; a wrong or shifted DEM loses most of that (selectivity ratio 0.44 for a wrong DEM, equal to image-only). This control passes **on the DEM-derived proxy**, which is circular (limitation 3).
* **Equalisation (vegetation in shadow vs. lit) is worse for TASC-DEM (0.012) than for TASC-image (0.197), global gamma (0.320) or CLAHE (0.62):** by this material-matched proxy the DEM-assisted variant does *not* equalise same-material brightness better; the evidence is mixed/negative. Held-out regions show the same sign (TASC-DEM -0.433 vs TASC-image -0.315).
* Held-out (Norway, NZ; sun elevation 7-20 deg, n = 2 regions): TASC-DEM lift in shadow 0.156 vs TASC-image 0.105, wrong DEM 0.113, beta-only 0.076, shifted 1 km 0.132; the selectivity ratio is noisy (0.41 vs 1.37; wrong DEM 1.88).

## Structure / spectra / highlights
* Shared gain preserves spectra: NDVI MAE 0.000-0.001 for all shared-gain TASC variants in Sentinel-2; per-band variants 0.139-0.181 and SAM 20.6-25.4 deg (vs 8.2 deg for TASC-DEM, no worse than the 8.9 deg of the unprocessed input). Zero-DCE: NDVI error 0.136, SAM 20.2 deg.
* Highlight distortion: TASC-image/TASC-DEM `bright_clip` = 0 in Sentinel-2, AID and iSAID; HE and AGC clip 48-62 % of bright pixels in AID/Sentinel-2.
* Halo (gradient-reversal) rate is higher for TASC-image than most baselines on AID (0.027 vs 0.001-0.002 for Zero-DCE/CLAHE) and iSAID (0.117 vs 0.008-0.037) and ExDark (0.040).
* Noise amplification: TASC-image amplifies noise least (0.43 DarkRS, 0.50 AID, 0.65 iSAID) because it lifts mainly through gamma on smoothed fields and suppresses the detail boost in dark regions; this partly reflects a flatter output, not only cleaner output (entropy/EME are also lowest).
* Seam/blockiness: smooth-field vs hard-block variants differ by <= 0.002 PSNR on D2 and AID (A1 vs A2); the guided filter does not matter measurably on these data.

## Not done
Shadow vs naturally-dark material is evaluated only through spectral-index material proxies in Sentinel-2; no manually annotated shadow masks exist.
