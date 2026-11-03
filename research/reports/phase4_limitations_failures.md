# Phase 4 — Failed experiments, deviations and limitations (nothing omitted)

## Failed or negative results (all preserved)
* Dev round 1 exposure (t_white 0.75, cap 0.5) lifted 72 % of clean AID-val images; PSNR on adequately exposed shadow-test images fell from 26.5 to 18.4 dB (`tables/phase4_dev/`).
* Dev gate G5: C2/C3 −6.5 dB vs TASC-v0-DEM on D2-val (2 crops); −9.5 dB on D2 test (6 crops). With uncapped exposure still −1.0 dB and local/DEM stages added ≤ 0.03 dB.
* C2b (evidence-gated exposure) failed G8 (|ΔY| ≥ 0.031 vs 0.02) in all 4 grid settings; kept as a post-hoc reported row.
* DEM guidance: no demonstrated benefit; proxy equalisation on Sentinel-2 *worse* with DEM (−0.038 vs +0.043).
* Real Sentinel-2 shadow/dark discrimination ratio unchanged (0.45 vs 0.49).
* Per-band global gamma and Zero-DCE beat TASC-v1 on AID and iSAID-dark.
* ExDark NIQE slightly worse than TASC-v0 (+0.20, p_Holm 0.04).

## Deviations from the pre-registration (all in `protocols/phase4_preregistration.md`)
A1 noise-clause amendment (original G3 verdict: fail); A2 new gate G8; A3 local thresholds chosen against the stated rule after seeing a terrain-test regression; A4 supplementary luminance-only metrics; A5 dev data limited to a scratch copy of AID-val (drive was initially unmounted) — Landsat/Sentinel-2 dev gates were run after the drive was attached; C2b added post hoc (beyond the three pre-registered candidates).

## Tooling defects found and fixed
* Phase 3 efficiency probe reported identical peak RSS (4 396 MB) for every method (`ru_maxrss` inherited across exec); replaced by per-process `VmHWM` (`trs/stages_p4.py`). Phase 3 memory column should be treated as invalid.
* First Phase 4 timing run omitted Zero-DCE (wrong constructor argument) and was re-run in full.
* An initial analysis merge mislabelled D2 TASC-v0 (Phase 3 "TASC-v0" is DEM-assisted); fixed with a dataset-specific rename and verified by an exact-match reproducibility check.

## Limitations
Landsat D2 = one scene, 6 crops, synthetic shadows (dev split 2 crops); Sentinel-2 evidence proxy-based and circular for DEM; no independent shadow annotations and no fresh test scenes; AID/iSAID low-light synthetic; AID degradation distorts colour (penalises ratio-preserving methods); one backbone for classification; no-reference metrics weakly related to utility; CPU-only timings; DFFN/SAGC/SAMSIE not evaluated; PDF built with WeasyPrint (no LaTeX toolchain installed, execution of a downloaded toolchain was refused earlier and was not bypassed), `.tex` is uncompiled.
