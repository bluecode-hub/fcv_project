# Statistical analysis (corrected)

* **Independent units** (after the audit pass, `scientific_corrections.md`): Landsat D2 = **6 source crops** of one Landsat scene (ten synthetic variants per crop averaged first); AID = 210 source images (three degradations averaged within image); E7 = each degradation analysed separately over 210 test images; iSAID-dark = **46 parent images** (crops/darkness levels averaged within parent); DarkRS = 86 images; ExDark = 400 images (same-series dependence cannot be excluded); Sentinel-2 = **regions** (tiles -> scenes -> regions): 4 development, 2 held out, 6 pooled.
* **Paired differences** between a reference method and each alternative on the same unit; 95 % percentile bootstrap CIs (10,000 resamples, `trs/stats.py`); two-sided Wilcoxon signed-rank only for n >= 5; **Holm** correction within each (reference, metric) family. Tables: `tables/*_vs_*.csv` (`diff`, `ci_lo`, `ci_hi`, `p`, `p_holm`, `ref_better_frac`).
* **D2 (n = 6):** the smallest attainable two-sided p is 0.031; with 27 comparisons per metric, p_Holm = 0.844 for every comparison with a unanimous sign. **No D2 comparison is statistically significant after correction.** Reported evidence: unanimous direction (6/6 crops) and bootstrap CIs over crops. The dependent variant-level analysis (60 pairs) is kept for transparency in `tables/d2_vs_tascv0_variant_level_dependent.csv` and must not be read as inference.
* **Sentinel-2:** no Wilcoxon p for 4 or 2 regions (`NaN`); six pooled regions give Holm-corrected p = 0.84-1.00. Exploratory only. All shadow masks derive from the DEM used by TASC-DEM (circular).
* **E7:** per-degradation bootstrap CIs of accuracy differences versus the degraded input; not corrected for multiple comparisons.
* Held-out regions were fixed before tuning (`protocols/sentinel2_regions.yaml`); no parameter was tuned on any held-out or test unit after the TASC-v0 freeze.
* 0 failures in every store; no unit excluded after the fact. Spectral-angle exclusions (clipped zeros, norm < 0.01) are pixel-level and counted in `tables/s2_sam_exclusions.csv`.

## Headline paired results (95 % bootstrap CI over independent units)
| Comparison | Unit (n) | Metric | Difference | CI | p_Holm |
|---|---|---|---|---|---|
| D2: TASC-v0 − global gamma | crop (6) | PSNR | +2.43 dB | 1.89..2.87 | 0.84 |
| D2: TASC-v0 − Zero-DCE | crop (6) | PSNR | +4.76 dB | 3.94..5.51 | 0.84 |
| D2: TASC-v0 − image-only | crop (6) | PSNR | +0.22 dB | 0.16..0.28 | 0.84 |
| D2: TASC-v0 − image-only | crop (6) | MAE shadow | −0.018 | −0.022..−0.013 | 0.84 |
| D2: TASC-v0 − image-only (dependent variants) | pair (60) | PSNR | +0.22 dB | −0.02..0.48 | 0.49 |
| AID: TASC-image − input | image (210) | PSNR | +1.19 dB | 0.64..1.73 | <0.001 |
| AID: TASC-image − global gamma | image (210) | PSNR | −4.15 dB | −4.53..−3.78 | <0.001 |
| AID: TASC-image − Zero-DCE | image (210) | PSNR | −4.94 dB | −5.40..−4.51 | <0.001 |
| AID: TASC-image − per-band global gamma (best) | image (210) | PSNR | −5.99 dB | −6.49..−5.52 | <0.001 |
| iSAID-dark: TASC-image − input | parent (46) | PSNR | −2.26 dB | −3.19..−1.36 | <0.001 |
| iSAID-dark: TASC-image − Zero-DCE | parent (46) | PSNR | −3.87 dB | −4.21..−3.54 | <0.001 |
| iSAID-dark: TASC-image − per-band global gamma (best) | parent (46) | PSNR | −4.89 dB | −5.12..−4.64 | <0.001 |
| DarkRS: TASC-image − input | image (86) | BRISQUE | +6.14 (worse) | 4.85..7.45 | <0.001 |
| DarkRS: TASC-image − input | image (86) | entropy | −0.42 | −0.47..−0.37 | <0.001 |
| ExDark: TASC-image − input | image (400) | NIQE | −0.56 (better) | −0.80..−0.31 | <0.001 |
| ExDark: TASC-image − input | image (400) | BRISQUE | +5.2 (worse) | 3.6..6.9 | <0.001 |
| Sentinel-2 dev: TASC-DEM − image-only | region (4) | shadow lift | +0.025 | −0.003..0.054 | n/a (n < 5) |
| Sentinel-2 all: TASC-DEM − image-only | region (6) | shadow lift | +0.034 | 0.011..0.056 | 1.00 |
