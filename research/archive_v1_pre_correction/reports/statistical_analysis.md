# Statistical analysis

* **Unit of analysis**: D2 test pair (60); AID test image (210; the three degradations of an image are averaged first); iSAID-dark image/level (138, see limitation 6); DarkRS image (86); ExDark image (400); Sentinel-2 **region** (tiles -> scenes -> regions; 4 development, 2 held-out, 6 pooled); E7 test image (210).
* **Paired differences** between a reference method and each alternative on the same unit; 95 % percentile bootstrap CIs (`trs/stats.py`, 10,000 resamples); two-sided paired Wilcoxon signed-rank tests with **Holm** correction within each (reference, metric) family. Tables: `tables/*_vs_*.csv` (columns `diff`, `ci_lo`, `ci_hi`, `p`, `p_holm`, `ref_better_frac`).
* **Sentinel-2**: with 4 (or 2) regions the smallest attainable Wilcoxon p-value is 0.125 (0.5), so no p-values are reported there (`NaN`); with all 6 regions the Holm-corrected p-values are 0.84-1.00. Differences there are described by CIs only and must be treated as exploratory.
* **E7**: accuracy differences versus Identity with 95 % bootstrap CIs over the 210 test images (`tables/downstream_vs_identity.csv`).
* Held-out regions were fixed before tuning (`protocols/sentinel2_regions.yaml`); no parameter was tuned on any held-out or test unit after the TASC-v0 freeze (the v0 parameters came from D2 validation).
* All 0 failures; no unit excluded after the fact. Full stores (JSONL) stay on the external drive; compact per-experiment summaries are in `tables/`.

## Headline paired results (95 % bootstrap CI; Holm p)
| Comparison | Metric | Difference | CI | p_Holm |
|---|---|---|---|---|
| D2: TASC-v0 - GlobalGamma | PSNR | +2.43 dB | 2.12..2.76 | <0.001 |
| D2: TASC-v0 - Zero-DCE | PSNR | +4.76 dB | 4.34..5.18 | <0.001 |
| D2: TASC-v0 - image-only | PSNR | +0.22 dB | -0.02..0.48 | 0.49 |
| D2: TASC-v0 - image-only | MAE shadow | -0.018 | -0.026..-0.009 | 0.001 |
| AID: TASC-image - Identity | PSNR | +1.19 dB | 0.64..1.73 | <0.001 |
| AID: TASC-image - GlobalGamma | PSNR | -4.15 dB | -4.53..-3.78 | <0.001 |
| AID: TASC-image - Zero-DCE | PSNR | -4.94 dB | -5.40..-4.51 | <0.001 |
| iSAID-dark: TASC-image - Identity | PSNR | -2.26 dB | -2.85..-1.71 | <0.001 |
| iSAID-dark: TASC-image - Zero-DCE | PSNR | -3.87 dB | -4.09..-3.66 | <0.001 |
| DarkRS: TASC-image - Identity | BRISQUE | +6.14 (worse) | 4.85..7.45 | <0.001 |
| DarkRS: TASC-image - Identity | entropy | -0.42 | -0.47..-0.37 | <0.001 |
| ExDark: TASC-image - Identity | NIQE | -0.56 (better) | -0.80..-0.31 | <0.001 |
| ExDark: TASC-image - Identity | BRISQUE | +5.2 (worse) | 3.6..6.9 | <0.001 |
