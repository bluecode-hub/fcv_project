# Benchmark-integrity controls

Every control runs through the same frozen v0 code path (adapter injects a different shadow field S or sun angle; `trs/adapter.py`, `trs/experiments.py`). Numbers are means over units; paired differences with 95 % bootstrap CIs are in `tables/*_vs_*.csv`.

## Landsat D2 (6 source crops × 10 variants = 60 pairs; unit = crop, n = 6; reference-based; PSNR dB / MAE in shadow)
*Statistics corrected in the audit pass (`scientific_corrections.md`): crop-level intervals; with n = 6 no comparison survives Holm correction (p_Holm = 0.84); all differences below point the same way in 6/6 crops.*
| Control | PSNR | MAE shadow | Reading |
|---|---|---|---|
| TASC-v0 (true DEM, true sun) | 21.65 | 0.130 | reference |
| No DEM (image-only) | 21.43 | 0.148 | DEM adds +0.22 dB (crop-level CI 0.16..0.28; at the dependent variant level CI -0.02..0.48) and lowers shadow MAE by 0.018 (CI 0.013..0.022); p_Holm = 0.84 at n = 6 |
| beta-only (S = 0) | 19.79 | 0.209 | -1.86 dB (CI 1.42..2.22): the shadow term matters, not just the constant lift |
| Flipped DEM | 20.45 | 0.187 | -1.20 dB: wrong terrain hurts |
| DEM shifted 720 m / 2.9 km | 21.25 / 20.65 | 0.150 / 0.179 | monotone degradation with misregistration |
| Sun azimuth +15 / -15 / +45 deg | 21.59 / 21.58 / 21.23 | 0.132 / 0.133 / 0.149 | small sensitivity to azimuth error |
| Sun elevation +7 / -7 deg | 21.07 / **22.45** | 0.153 / **0.102** | **-7 deg beats the true metadata**: PSNR rewards a larger shadow field on under-exposed images; metric is not a measure of geometric correctness |
| Without DCT detail boost | 21.77 | 0.124 | removing the DCT detail step is slightly *better* on PSNR (+0.12 dB, CI 0.10..0.14) and MAE; LPIPS 0.198 vs 0.202 |
| Global gamma + DCT (A0) | 20.27 | 0.209 | v0 beats A0 by 1.37 dB (CI 0.91..1.64) |
| Per-band gamma (no shared gain) | 15.25 | 0.131 | -6.40 dB; NDVI error 0.162 vs 0.018 (shared gain preserves ratios) |
| Identity, GlobalGamma, per-band GlobalGamma, Zero-DCE | 7.78, 19.22, 12.12, 16.89 | 0.468, 0.224, 0.225, 0.297 | v0 beats all non-TASC baselines (6/6 crops) |

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
* **Spectra (corrected metric, see `scientific_corrections.md`).** Output-vs-input spectral angle, NDVI/NDWI error and band-ratio deviation are exactly 0 for every shared-gain method (TASC image-only/DEM and ablations, global gamma, CLAHE+shared, AGCWD+shared) on Sentinel-2 and D2, identical to the input compared with itself. This is an algebraic property of one gain per pixel and is not evidence of superiority over the input. Non-shared-gain methods (Sentinel-2 development / held-out regions): per-band global gamma 10.3° / 7.0°, CLAHE 6.8° / 6.8°, AGC 11.7° / 5.8°, AGCWD 4.2° / 3.9°, HE 12.7° / 10.1°, per-band TASC 13.8° (DEM) and 19.2° (image-only) / 11.0° and 12.0°, C-correction 2.5° / 4.4°, SCS+C 2.4° / 4.4°, Zero-DCE 2.1° / 2.3° (NDVI error 0.025 / 0.027). Pixels with zero or near-zero vectors are excluded and counted (`tables/s2_sam_exclusions.csv`; ~10 % of valid pixels for the input, ~21 % for Zero-DCE). On D2, reconstruction accuracy vs the clean reference: every shared-gain method has 1.52° (inherited from the degraded input), Zero-DCE 3.46°, per-band methods 10.7–15.9°.
* Highlight distortion: TASC-image/TASC-DEM `bright_clip` = 0 in Sentinel-2, AID and iSAID; HE and AGC clip 48-62 % of bright pixels in AID/Sentinel-2.
* Halo (gradient-reversal) rate is higher for TASC-image than most baselines on AID (0.027 vs 0.001-0.002 for Zero-DCE/CLAHE), iSAID (0.117 vs 0.008-0.037) and ExDark (0.040).
* Noise amplification: TASC-image has the lowest noise amplification of the shared-gain methods on DarkRS (0.43, lowest of all methods) and AID (0.50; per-band TASC variant 0.40), but not on iSAID-dark (0.65; global gamma 0.60) or ExDark (0.78; global gamma 0.69). It lifts mainly through gamma on smoothed fields and suppresses the detail boost in dark regions; this partly reflects a flatter output, not only cleaner output (its EME is lowest on DarkRS and its entropy second-lowest after 2D-gamma).
* Seam/blockiness: smooth-field vs hard-block variants differ by 0.015 dB PSNR on D2 (A1 vs A2) and 0.10 dB on AID; the guided filter does not matter measurably on these data.

## Not done
Shadow vs naturally-dark material is evaluated only through spectral-index material proxies in Sentinel-2; no manually annotated shadow masks exist. All Sentinel-2 shadow masks are derived from the DEM that TASC-DEM uses (circularity).
