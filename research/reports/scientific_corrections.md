# Scientific corrections (audit pass after the first draft)

Original draft: commit `561f326` (kept verbatim in `research/archive_v1_pre_correction/`; the original JSONL stores on the external drive are untouched). Frozen `tasc/` sources are unchanged (`git diff TASC-v0 -- tasc` is empty).

## 1. Spectral-angle (SAM) defect
**What was wrong.** `tasc.metrics.sam_deg` (frozen, used by the research metrics) returned 8.93° for the *unprocessed* Sentinel-2 input compared with itself (dev regions; 5.99° held-out, 7.95° over six regions). Verified causes (diagnosis on one Ladakh tile: identical input, `sam_deg` = 24.4°):
1. **Zero vectors.** Reflectance is DN × scale + offset, clipped to [0, 1]; deep shadow, clear water and snow-free dark pixels become exactly 0 in all bands. For a = b = 0 the code gives cos = 0/(0 + EPS) = 0, i.e. **90°**. In that tile 24.9 % of the pixels had zero norm.
2. **EPS in the denominator.** `den = |a||b| + 1e-6` biases cos below 1 by EPS/|a||b|; for identical vectors the angle is ≈ √(2·EPS)/|a| rad (0.8° at |a| = 0.1, 26° on average for 0 < |a| < 0.01).
3. **float32 `arccos` near 1** adds a further resolution error (the mean angle was still 0.54° for |a| ≥ 0.1).
The same zero/near-zero pixels also inflated the **NDVI/NDWI errors** (a pixel that is 0 in the input but lifted by a method counted as a large index error) and the **band-ratio deviation** (epsilon 1e-4 inside logs).

**What changed.** New evaluation module `research/trs/spectral.py` (frozen code untouched): float64, angle = 2·asin(|â − b̂|/2), no epsilon, pixels excluded when invalid, when either vector has norm < 0.01 (sensitivity 0.03) — and, for NDVI/NDWI, when the two bands sum to < 0.02, for log ratios when any band < 0.005 — with counts of valid, used and excluded pixels stored per row. Tests (`research/tests/test_sam.py`, 8): identical images, positive scalar multiples (gain invariance), known angles (45°, 60°, 90°, 180°), zero/tiny vectors excluded and counted, mask exclusions counted, an all-zero input yields NaN rather than 0, the frozen defect reproduced, shared-gain invariance through TASC, index/ratio metrics invariant to gain and to lifted zero pixels. Sentinel-2 (6,264 rows) and Landsat D2 (1,680 rows) were re-evaluated by re-running the methods (outputs were not stored) into new stores `e_sentinel2_spectral`, `e_landsat_d2_spectral` (0 failures); the original stores keep the old columns, and the analysis keeps them as `*_orig_defective`. The full six-hour batch was not repeated.

**Before → after (region means; output versus input unless stated).**
| Method | SAM dev before → after | SAM held-out before → after | NDVI err dev before → after |
|---|---|---|---|
| Identity (input vs itself) | 8.93° → **0.00°** | 5.99° → 0.00° | 0 → 0 |
| TASC-DEM | 8.21° → 0.00° | 5.34° → 0.00° | 0.001 → 0.000 |
| TASC image-only | 8.12° → 0.00° | 5.30° → 0.00° | 0.000 → 0.000 |
| Global gamma | 8.14° → 0.00° | 5.31° → 0.00° | 0 → 0 |
| AGCWD + shared gain | 20.28° → 0.00° | 18.92° → 0.00° | 0.128 → 0.000 |
| Zero-DCE | 20.21° → 2.13° | 18.22° → 2.34° | 0.136 → 0.025 |
| CLAHE (per band) | 14.62° → 6.78° | 12.08° → 6.84° | 0.081 → 0.075 |
| AGCWD (per band) | 12.33° → 4.17° | 9.26° → 3.91° | 0.049 → 0.052 |
| HE | 20.05° → 12.73° | 15.19° → 10.11° | 0.123 → 0.136 |
| C-correction | 10.84° → 2.52° | 10.18° → 4.45° | 0.020 → 0.025 |
| TASC-DEM per band | 20.64° → 13.81° | 15.59° → 11.00° | 0.139 → 0.150 |
Landsat D2 (reference-based, no zero pixels): SAM to the clean reference changes by ≤ 0.04° (TASC-v0 1.523° → 1.521°, Zero-DCE 3.462° → 3.462°, HE 17.567° → 17.531°); NDVI error unchanged to 3 decimals. New D2 columns: SAM to the *input* (preservation; 0.00° for shared-gain methods).

**Did conclusions change?** Yes, for spectral claims:
* *Withdrawn:* "TASC's spectral angle (8.2°) is no worse than — or better than — the unprocessed input (8.9°)". Corrected: output-vs-input SAM is **0° for every shared-gain method, identical to the input compared with itself**; this is an algebraic property of multiplying all bands of a pixel by one factor, not an empirical advantage, and the metric does not discriminate among shared-gain methods.
* *Weakened:* "Zero-DCE destroys spectra (NDVI 0.136, SAM 20.2°)". Corrected: 2.1–2.3° and NDVI error 0.025–0.027. It does change spectra, far less than per-band methods (7–19°).
* *Corrected:* "all shared-gain TASC variants have NDVI error ≤ 0.001" → exactly 0 on valid pixels; "AGCWD+shared changes spectra (20°)" → 0°.
* *Unchanged:* per-band methods change spectra by large amounts (HE 12.7°, AGC 11.7°, per-band global gamma 10.3°, per-band TASC 13.8–19.2°); reconstruction accuracy against ground truth on D2 (TASC inherits the degraded input's 1.52° error).
* Added caveat: band-ratio preservation is **not** recovery of surface reflectance.

## 2. Statistical units (dependence)
* **Landsat D2:** the 60 pairs are 6 source crops of **one** Landsat scene × 10 synthetic illumination variants. Variants are dependent; the unit is now the source crop (n = 6, variants averaged). Consequence: the smallest attainable Wilcoxon p is 0.031, and after Holm correction (27 comparisons) every D2 comparison has p_Holm = 0.84 — **no D2 comparison is significant after correction** (the earlier "p_Holm < 0.001" claims are withdrawn). Direction is consistent in 6/6 crops, and bootstrap intervals over crops exclude 0 (TASC-v0 − global gamma +2.43 dB, CI 1.89–2.87; − Zero-DCE +4.76, 3.94–5.51; DEM − image-only +0.22, 0.16–0.28; shadow MAE −0.018, −0.022 to −0.013). The earlier variant-level analysis is kept as `tables/d2_vs_tascv0_variant_level_dependent.csv` (DEM − image-only +0.22 dB, CI −0.02 to 0.48 at variant level).
* **iSAID-dark:** 138 files → 46 parent images (crops of one parent and the three darkness levels averaged). TASC − input: −2.26 dB, CI now −3.19 to −1.36 (was −2.85 to −1.71); − Zero-DCE −3.87 (−4.21 to −3.54).
* **AID, E7:** repeated degradations were already averaged per source image (AID) or analysed per degradation (E7); unchanged.

## 3. "Best baseline" claims (per-band baselines included)
* AID: the best baseline on every full-reference metric is **per-band global gamma** (PSNR 17.51, SSIM 0.490, LPIPS 0.555), not Zero-DCE (16.46 / 0.420 / 0.575). The Table V bold marking and the text were corrected; TASC-image is 5.99 dB below the best baseline (CI −6.49 to −5.52).
* iSAID-dark: best PSNR is per-band global gamma (14.40 dB); TASC-image is 4.89 dB below it.
* Sentinel-2: "TASC-DEM has the largest shadow lift" now restricted to spectra-preserving methods with true sun angles; AGC (0.212), HE (0.193) and per-band variants (0.30–0.33) lift similarly or more but change spectra or clip highlights.
* DarkRS: TASC-image is *not* the lowest-entropy method (2D-gamma 5.71 < 6.06); ExDark: TASC-image is *not* the lowest-noise-amplification method (global gamma 0.69 < 0.78). Corrected in text.
* D2: "best of all methods" restricted to non-TASC baselines; TASC ablations (e.g. elevation −7°, no-DCT) can score higher.

## 4. Other corrections
* Related work: SAGC (Huang et al., Infrared Phys. Technol. 94, 2018, doi:10.1016/j.infrared.2018.08.019) and SAMSIE (Huang et al., Infrared Phys. Technol. 121, 2022, doi:10.1016/j.infrared.2021.104014) were verified against Crossref and added; they were *not* evaluated. DFFN's description corrected (the previous text asserted it "introduces iSAID-dark"; its authors state that they built two low-light RS datasets). No novelty is claimed for spatially adaptive gamma or terrain-aware enhancement.
* Manuscript build: the first PDF silently lost equations (`\bigl/\bigr` are not supported by matplotlib mathtext, and equations were rescaled). Fixed; regression tests render every display equation and check that each appears in both the `.tex` and the HTML; numbers in tables and key text claims are checked against the CSVs (`scripts/verify_manuscript_numbers.py`, 416 checks, 0 mismatches). The PDF is a WeasyPrint rendering (fallback); a real IEEEtran compile was blocked (the sandbox policy refused to run the downloaded tectonic binary), so `first_draft.tex` is **uncompiled**.
* Figures regenerated from the corrected tables and extended with the per-band baselines; the D2 figure now states its unit.
