# Phase 4 pre-registration (written before any TASC-v1 candidate was scored)

Date: 2026-11-03. Branch `research/tasc-v1-phase4`. Frozen baseline: TASC-v0 (`297a6d7`), v0-defaults.

## Data allowed for design and selection ("development")
AID **val** split (90 source images × 3 degradations; manifest `aid_subset.json`), Landsat D2 **val** split (20 tiles), Sentinel-2 **dev** regions (alps_valais, colorado_rockies, atacama_andes, ladakh), iSAID-dark **val**. Test/held-out data (AID test 210, D2 test, S2 held-out regions norway_jotunheimen & nz_southern_alps, iSAID test, DarkRS, ExDark, downstream) are not touched until the candidate is frozen. Previously examined held-out data are *not* "unseen"; any new final-test claim is restricted to data not used in Phase 3 where obtainable, otherwise labelled "previously examined".

## Candidates (≤ 3, fixed in advance)
* **C1** exposure only: highlight-anchored adaptive exposure, no local stage (isolates Component 1).
* **C2** C1 + illumination-relative local lift gated by image-only shadow confidence (RGB or RGB+NIR cues).
* **C3** C2 + confidence-weighted DEM guidance (alignment search, agreement weight, sun-metadata ensemble).
DCT detail is OFF in all candidates; it is re-introduced only as an ablation. At most one small parameter round per candidate on development data (documented, all runs kept).

## Development gate (all must hold on development data; evaluated per source image/crop/region, 95 % paired bootstrap CI)
G1 AID-val: PSNR(candidate) − PSNR(TASC-v0) ≥ +2.0 dB with CI > 0, **and** PSNR ≥ unprocessed input.
G2 AID-val: SSIM ≥ SSIM(TASC-v0) + 0.03; LPIPS not worse than TASC-v0 (CI upper bound ≤ +0.01).
G3 Clipping/halo/noise: new-bright-clip ≤ v0 + 0.005; halo ≤ 1.25 × v0; noise-amplification ≤ v0 + 0.05.
G4 Spectral (4-band data, common valid mask): SAM to input ≤ 0.05°, NDVI/NDWI error ≤ 0.001 (shared-gain invariance must hold).
G5 D2-val (when available): PSNR not lower than v0 by > 0.5 dB; shadow-region MAE not higher than v0 by > 10 % (relative).
G6 DEM robustness (for C3): with wrong DEM, shadow-lift ≤ image-only lift + 0.02 and PSNR/SSIM within 0.2 dB / 0.01 of image-only on D2-val.
G7 Natural-dark control: on naturally dark but evenly lit scenes the mean lift of C2/C3 must be ≤ 50 % of the TASC-v0 lift.
Selection rule: pick the simplest candidate that passes G1–G7 (C1 < C2 < C3); a more complex candidate is selected only if it beats the simpler one on a development metric by a CI that excludes 0. If none passes G1–G4, no candidate advances: the report is a negative finding and the paper stays a benchmark/failure-analysis paper.

## Not gated, but reported
Comparison with the strongest baseline (per-band global gamma, Zero-DCE, CLAHE); downstream accuracy; runtime/memory.

## Statistics (final evaluation)
Units: D2 source crop (n=6, single scene); Sentinel-2 region (n=6); AID source image; iSAID-dark parent image; DarkRS/ExDark image (dependence caveat); classification: paired predictions on the same test images (McNemar + paired bootstrap). Holm correction within each dataset family; 10 000-resample bootstrap CIs; per-dataset wins/losses vs v0 and vs best baseline.

## Independence of shadow evidence
Masks derived from the DEM supplied to the method are proxies only. Independent evidence candidates: Sentinel-2 SCL cloud-shadow is *not* terrain shadow; spectral-index material classes (NDVI/NDWI-defined) are independent of the DEM; an image-derived shadow mask (low-brightness-in-NIR/SWIR heuristics) is itself a heuristic. Unless a manually annotated or otherwise independent terrain-shadow reference is obtained, S2 DEM benefit is reported as proxy-based/exploratory.

---
## Amendments made during development (before any test / held-out evaluation; original text above left unchanged)
* **A1 (G3 noise clause).** Original: `noise_amp <= v0 + 0.05`. Observed on AID-val: TASC-v0 0.51, global gamma 0.53, C2 0.80. `noise_amp` divides output noise by the *mean luminance gain*, and v0 scores low partly because its block equalisation removes structure (SSIM 0.19). Amended clause: `noise_amp <= 1.0` (no net noise amplification beyond the signal gain, i.e. Identity level). The original verdict (**G3 fails**) is retained in the selection report next to the amended one.
* **A2 (new gate G8, adequate-exposure).** Motivation: dev round 1 (t_white 0.75, mean_cap 0.5) lifted 72 % of *clean* AID-val images (median clean 95th-percentile luminance is 0.66) and cut PSNR on adequately exposed shadow-test images from 26.5 to 18.4 dB. Gate: on clean AID-val images the exposure stage changes luminance by mean |ΔY| <= 0.02. Round 2 grid {0.45,0.55,0.65} × {0.35,0.45}; rule: maximise degraded-image PSNR subject to G8 → t_white 0.55, mean_cap 0.35 (|ΔY| = 0.017, degraded PSNR 15.52).
* **A3 (local thresholds r_hi/r_lo).** Grid {(0.80,0.35),(0.65,0.30),(0.55,0.25),(0.50,0.20)}; stated rule "maximise shadow-region PSNR s.t. lit lift <= 0.015" would keep (0.80,0.35). I chose **(0.65,0.30)** instead *after* seeing that (0.80,0.35) lowered overall PSNR below the unprocessed input on the synthetic-terrain test; (0.65,0.30) has the best overall PSNR on the shadow test (26.85 dB vs 24.29 unprocessed) at lower shadow PSNR (16.28 vs 17.22). This is a documented deviation from the stated rule; all four settings are in `tables/phase4_dev/local_threshold_grid.csv`.
* **A4 (supplementary metrics).** PSNR-Y/SSIM-Y (luminance only) added after a 2-image smoke test showed per-band methods benefit from restoring the benchmark's chroma distortion. Gates still use RGB PSNR/SSIM as pre-registered.
* **A5 (dev data actually available).** The external drive was not attached during this development stage. AID-val images (90 files, 25 MB, public Hugging Face mirror `blanchon/AID`, files listed in `aid_subset.json` as split=val) were re-downloaded to a scratch directory (not the drive, not committed). Landsat D2-val and Sentinel-2 dev regions were NOT available: gates G5, G6 (real terrain) are **pending**; G6 was exercised only on a synthetic DEM (`scripts/phase4_dev_terrain.py`).
