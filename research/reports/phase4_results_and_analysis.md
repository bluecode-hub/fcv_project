# Phase 4 — Results and analysis (what we actually achieved)

Source of every number: `research/tables/phase4/*.csv`, `comparisons.csv` (all comparators, all metrics, bootstrap CIs, Holm), `analysis_status.json` (reproducibility check: recomputed TASC-v0 and Identity rows equal the Phase 3 stores to 0.0 on AID, D2, Sentinel-2). Frozen candidates: C1 (exposure), C2 (image-only TASC-v1), C3 (DEM-assisted), post-hoc C2b. **No candidate passed the pre-registered development gate** (G5 failed on Landsat D2-val); the evaluation below is diagnostic. All final-evaluation data were previously examined in Phase 3 (not newly unseen).

## TASC-v1 (C2 / C3) versus TASC-v0, per dataset
| Dataset (unit, n) | Metric | TASC-v0 | TASC-v1 | Δ [95 % CI] | Verdict |
|---|---|---|---|---|---|
| AID (image, 210) | PSNR | 11.51 | 14.86 | +3.35 [2.74, 3.99] | better |
| AID | SSIM / LPIPS | 0.211 / 0.763 | 0.374 / 0.584 | +0.163 / −0.179 | better |
| iSAID-dark (parent, 46) | PSNR | 9.51 | 11.96 | +2.45 [1.86, 3.00] | better; ≈ input (+0.19, CI −0.36…0.69) |
| Landsat D2 (crop, 6) | PSNR | 21.43 (img) / 21.65 (DEM) | 11.90 (C2) / 11.97 (C3) | −9.53 / −9.75 | **much worse** (n = 6, one scene; no corrected significance possible) |
| D2 | shadow MAE | 0.148 / 0.130 | 0.355 / 0.347 | worse | worse |
| Sentinel-2 (region, 6; proxy) | shadow lift | 0.164 / 0.198 | 0.053 / 0.057 | −0.110 / −0.140 | much weaker enhancement |
| DarkRS (image, 86) | NIQE / entropy | 9.24 / 6.06 | 9.18 / 6.83 | −0.06 (ns) / +0.78 | entropy up; NIQE unchanged |
| ExDark (image, 400) | NIQE / entropy | 11.71 / 5.88 | 11.90 / 6.36 | +0.20 (p_Holm 0.04, worse) / +0.48 | mixed |
| AID classification (n = 210) | accuracy u/n/s | .638/.705/.343 | .829/.857/.648 | +19.0/+15.2/+30.5 pp (p_Holm < .001) | better |

## Versus the strongest baselines
Per-band global gamma (AID 17.51, iSAID 14.40 dB) and Zero-DCE (16.46 / 13.38) beat TASC-v1 on every reference-based metric (AID −2.64 and −1.59 dB; iSAID −2.44 and −1.42 dB; all p_Holm < 10⁻⁷). On D2 simple global gamma (19.22 dB) beats TASC-v1 by 7.3 dB. **TASC-v1 does not outperform the best baselines anywhere.** Per-band methods change spectra (SAM 7–9° on Sentinel-2), TASC-v1 does not (0°).

## Answers to the ten questions
1. **Improved over TASC-v0?** On synthetic low light (AID, iSAID), classification and entropy: yes. On terrain shadows (D2) and shadow lift (Sentinel-2): no.
2. **Largest component:** exposure. Removing it costs 4.4 dB on AID; local stage +0.04 dB (AID) / +0.24 dB (D2); chroma cue ±0.01 dB; DCT ±0.03 dB; DEM +0.07 dB (D2).
3. **Did adaptive exposure resolve the AID/iSAID failures?** Partly. The collapse is repaired (AID +4.5 dB over the input; iSAID no longer below the input) but a v0-style fixed target *without the block stage* scores higher on AID (15.76 vs 14.86); the adaptive rule is protective, not an accuracy gain, and it conflicts with Landsat D2.
4. **Natural dark surfaces less enhanced?** Synthetic shadows: dark-to-shadow lift ratio 0.29 vs 0.69 (v0). Real Sentinel-2: ratio 0.45 vs 0.49 — unchanged; TASC-v1 just enhances less.
5. **DEM benefit beyond image-only?** Not demonstrated: D2 +0.07 dB (one scene), Sentinel-2 shadow lift +0.004 but proxy equalisation −0.081 (CI −0.162…−0.009). Trust weight works defensively (wrong/shifted DEM ≈ image-only; without trust, equalisation −0.181).
6. **Independent of DEM-generated masks?** No independent terrain-shadow masks were obtained; all Sentinel-2 analysis is proxy-based and exploratory.
7. **Multispectral information preserved?** Yes (SAM, NDVI/NDWI, band ratios to the input = 0 exactly) — by algebraic construction; not reflectance recovery.
8. **Downstream classification?** Preserved relative to the input (−1.0, 0.0, +6.7 pp; none significant after Holm), restored relative to TASC-v0.
9. **Versus stronger baselines?** Loses (see above).
10. **Remaining limitations:** see `phase4_limitations_failures.md`.

## Contribution classification
| Contribution | Status |
|---|---|
| Highlight-anchored adaptive exposure | Partially supported |
| Evidence-gated local lift (shadow vs dark material) | Inconclusive (synthetic support only) |
| Trust-weighted DEM guidance: robustness to wrong/shifted DEM | Supported |
| Trust-weighted DEM guidance: physical benefit | Unsupported |
| DCT removal | Supported |
| Shared gain preserves spectra | Supported as a property; reflectance recovery unsupported |
| TASC-v1 as improved successor to TASC-v0 | **Unsupported** |

## Recommendation
Retain the work as a **benchmark / failure-analysis paper** (TASC-v0 failure modes, corrected metrics, the exposure-prior conflict between datasets, the null DEM result). Do not present TASC-v1 as a breakthrough.
