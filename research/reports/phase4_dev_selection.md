# Phase 4 development-stage selection (frozen before any test / held-out evaluation)

Data: AID **validation** split only (90 source images × 3 degradations; scratch copy) + two synthetic dev tests built from the same 90 images (known soft shadows; synthetic DEM terrain). Unit = source image; 95 % paired bootstrap (10 000). Pre-registration: `protocols/phase4_preregistration.md` (amendments A1–A5 listed there). Raw dev tables: `tables/phase4_dev/`.

## Defaults frozen for TASC-v1 (`research/v1/config.py`)
`exp_q=95, t_white=0.55, mean_cap=0.35, gamma_min_global=0.35`; `ill_percentile=80, ill_window_frac=0.25, r_hi=0.65, r_lo=0.30, chroma_tau=0.30, water_penalty=0.8, target_kappa=0.9, gamma_min_local=0.40`; DEM: `dem_shift_search_px=24, rho0=0.10, rho1=0.40, sun_ensemble=3 perturbations`; `detail=False`; shared gain with cap 6 and soft knee 0.85/0.97.
Parameter rounds actually run (all kept): exposure grid round 1 (9 settings), exposure round 2 (6 settings, adds G8), local-threshold grid (4 settings). No test or held-out data were used.

## Results on AID-val (degraded; RGB PSNR/SSIM; Δ vs TASC-v0, CI over source images)
| Method | PSNR | SSIM | LPIPS | Δ PSNR vs v0 | Δ SSIM vs v0 |
|---|---|---|---|---|---|
| Identity | 10.63 | 0.243 | 0.609 | −0.44 [−1.22, 0.33] | +0.054 |
| TASC-v0 | 11.07 | 0.189 | 0.797 | – | – |
| TASC-v0 / no global exposure | 15.81 | 0.298 | – | +4.73 [4.21, 5.24] | +0.109 |
| Global gamma (shared gain) | 15.84 | 0.290 | 0.680 | +4.76 | +0.101 |
| Global gamma per band | **17.83** | **0.473** | **0.584** | +6.76 | +0.284 |
| **C1 exposure only** | 15.52 | 0.360 | 0.604 | +4.44 [3.59, 5.26] | +0.171 [0.160, 0.182] |
| **C2 (exposure + local gated lift)** | 15.54 | 0.359 | 0.608 | +4.47 [3.62, 5.28] | +0.171 [0.159, 0.182] |
| C2 / no exposure | 10.75 | 0.257 | – | −0.33 | +0.069 |
| C2 / v0-style fixed exposure (mean→0.55) | 15.94 | 0.328 | – | +4.86 | +0.139 |
| C2 / + DCT detail | 15.56 | 0.362 | – | +4.49 | +0.174 |
| C2 / no chroma cue | 15.53 | 0.358 | – | +4.46 | +0.169 |
| C2 / per-band | 17.07* | 0.457 | – | +6.01 | +0.268 |
(*round-2 value; round-3 table in `tables/phase4_dev/aid_val_analysis_final.md`.) LPIPS: C2 − v0 = −0.189 [−0.213, −0.165].

### What the AID-val result does and does not show
* **Supported:** removing the fixed-target exposure / unconditional block equalisation fixes TASC-v0's AID collapse (+4.5 dB, SSIM +0.17, LPIPS −0.19); C1 and C2 now exceed the unprocessed input by ≈ 4.9 dB.
* **Not supported:** that the *adaptive* exposure rule is the cause. v0's own mean→0.55 rule *without* the block stage gives equal or slightly higher PSNR on degraded images (15.94 vs 15.54) — the adaptive rule's advantage is only on already-adequate images (G8; shadow test below).
* **Not supported:** that the local gated stage helps on AID (C2 − C1 = +0.02 dB). AID has no systematic illumination shadows; this is expected, not a result for the shadow claim.
* **Per-band global gamma is still ≈ 2.3 dB better (RGB PSNR) and has better SSIM/LPIPS.** Part of this is the benchmark's per-channel gamma degradation (see baseline audit), but luminance-only PSNR-Y also favours global gamma (18.66 vs 16.54), so TASC-v1 does **not** beat the strongest simple baseline on AID.

## Synthetic shadow test (known multiplicative soft shadows on clean AID-val; synthetic)
| Method | PSNR all | PSNR in shadow | lift shadow | lift natural-dark (unshadowed) | lift lit |
|---|---|---|---|---|---|
| Identity | 24.29 | 11.65 | 0 | 0 | 0 |
| TASC-v0 | 13.76 | 14.75 | 0.381 | 0.263 | 0.214 |
| C1 | 23.00 | 12.59 | 0.015 | 0.018 | 0.021 |
| **C2** | **24.93** | 16.82 | 0.144 | 0.042 | 0.028 |
| C2 / no chroma cue | 23.85 | 17.21 | 0.167 | 0.065 | 0.033 |
| C2 / no exposure | 26.85 | 16.28 | 0.132 | 0.025 | 0.007 |
C2 − C1 in shadow PSNR +4.23 dB [3.60, 4.88]; C2 − v0 +2.08 [0.78, 3.41]; C2 − Identity (overall) +0.64 [−0.53, 1.74] (not significant). Natural-dark/shadow lift ratio: C2 0.29, v0 0.69, no-chroma 0.39. The chroma cue lowers natural-dark lift by ≈ 35 % at a small cost in shadow PSNR (−0.39 dB [−0.62, −0.19]) but raises overall PSNR (+1.08 [0.71, 1.50]).
Honest limits: shadows here are pure multiplicative factors (the model TASC assumes), and natural-dark pixels are the darkest 15 % of the clean image, which includes genuinely shadow-like dark objects.

## Synthetic terrain test (synthetic DEM + sun; circular for the correct DEM by construction)
Shadow PSNR vs C2 (image-only): correct DEM +0.48 dB [0.27, 0.68]; DEM shifted 24 px +0.43 [0.23, 0.63] (shift search recovers it); **wrong DEM +0.00 [0.00, 0.01]** (trust → 0); wrong DEM *without* the trust weight: overall PSNR −0.12 [−0.17, −0.07]. Shadow fraction was only 1.1 %, so overall PSNR of C2/C3 (24.93–24.98) is **below** the unprocessed input (26.78): when shadows are rare the exposure stage (on the 25 % of images with 95th percentile < 0.55) and the weak local lift cost more than they gain.

## Gates (dev)
| Gate | C1 | C2 | C3 |
|---|---|---|---|
| G1 PSNR ≥ v0 + 2 dB, CI > 0, ≥ Identity (AID-val) | pass (+4.44) | pass (+4.47) | n/a (no DEM on AID) |
| G2 SSIM ≥ v0 + 0.03 and LPIPS not worse | pass | pass | n/a |
| G3 clip/halo/noise — **original clause** (noise ≤ v0 + 0.05) | **fail** (0.81 vs 0.51) | **fail** (0.80) | – |
| G3 — amended clause A1 (noise ≤ 1.0) | pass | pass | – |
| G4 spectral (shared-gain invariance) | pass in unit tests (SAM < 1e-3°, NDVI/ratio dev < 1e-5); **real 4-band data pending** | same | same |
| G5 D2-val no regression | **pending (drive)** | pending | pending |
| G6 wrong-DEM robustness | n/a | n/a | pass on synthetic DEM; **real DEM pending** |
| G7 natural-dark lift ≤ 50 % of v0 | n/a (no local stage) | pass (0.042 vs 0.263) | pass (0.041) |
| G8 adequate-exposure (A2) | pass (|ΔY| 0.017) | pass | pass |

## Selection
1. **Image-only TASC-v1 = C2.** Simplest candidate that passes G1–G3(amended)/G7/G8 *and* beats C1 on a dev metric with a CI excluding 0 (shadow test: +4.23 dB [3.60, 4.88]).
2. **DEM-assisted TASC-v1 = C3, conditional.** On synthetic terrain C3 beats C2 (+0.48 dB shadow PSNR, CI excludes 0) and is robust to wrong/shifted DEMs, but G5/G6 on real Landsat D2-val and Sentinel-2 dev data cannot be evaluated until the external drive is attached. C3 is advanced to the final evaluation only if those two dev gates pass; otherwise DEM guidance is reported as not demonstrated.
3. DCT detail: **removed** (C2 + DCT: +0.02 dB on AID-val, −0.18 dB overall PSNR on the shadow test; v0 audit already showed no benefit).
4. Per-band variant: not selected (changes spectra by construction); reported as an ablation.
