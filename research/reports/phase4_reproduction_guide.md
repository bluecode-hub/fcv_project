# Phase 4 — Reproduction and supplementary methodology

Environment: Python 3.12 venv (`numpy, scipy, opencv-contrib, torch (CPU), pandas, scikit-learn, lpips`), CPU only, 16 GB RAM. External drive layout as in `research/trs/paths.py` (`TASC_Research/`); datasets, stores and weights are **not** in git.

1. Tests (no data needed): `python -m pytest research/v1/tests -q` (26 tests; includes the frozen-`tasc/` diff test) and `research/tests`.
2. Development scripts (`research/scripts/phase4_dev_*.py`): AID-val, exposure grids, synthetic shadow/terrain tests, real-terrain dev run (`phase4_dev_real.py d2|s2`). Results: `research/tables/phase4_dev/`; decisions: `reports/phase4_dev_selection.md` (committed before test evaluation).
3. Final evaluation as a persistent service: `research/scripts/launch_phase4.sh` (systemd --user, MemoryHigh 9 G / Max 11 G, ≤ 2 workers, resumable JSONL stores `p4_*`, preflight checks drive, committed selection, tests, frozen v0 and ≥ 5 GB free RAM). Status: `experiment_outputs/phase4_stage_status.json` (copy in `tables/phase4/stage_status.json`; all stages done, 0 failures).
4. Statistics: `python -c "from research.trs import analysis_p4 as A; A.run()"` → `research/tables/phase4/`.
5. Figures: `research/scripts/make_phase4_figures.py`. Manuscript: `python research/scripts/build_manuscript.py --src tasc_v1_phase4` → `.tex` (IEEEtran, uncompiled) and `.pdf` (WeasyPrint fallback).
6. Efficiency: `trs/stages_p4.stage_efficiency` (one fresh process per method, VmHWM, 1024², 4 threads).
Seeds: 20261101 (degradations and splits from Phase 3, unchanged). TASC-v1 is deterministic.
Excluded from git: datasets, LPIPS/AlexNet and Zero-DCE weights, scratch copies of AID-val.
