# Reproduction guide

1. **Environment**: Python 3.12 venv with `numpy scipy scikit-image opencv-contrib-python-headless rasterio pandas torch torchvision lpips pystac-client scikit-learn matplotlib pytest pyyaml shapely` (CPU PyTorch is sufficient). `weasyprint markdown` for the PDF.
2. **Drive**: an external volume mounted at `/run/media/ayaan/New Volume` (edit `research/trs/paths.py` for another location) with >= 100 GB free. `check_drive()` creates `TASC_Research/{datasets,cache,checkpoints,experiment_outputs,manifests,logs}`.
3. **Data**: Landsat D1/D2 `python research/scripts/prepare_landsat.py`; AID `python research/scripts/fetch_aid.py`; Sentinel-2 + DEM `python research/scripts/fetch_sentinel2.py` (public S3, no credentials); iSAID-dark (DFFN README Google Drive link), DarkRS and ExDark must be downloaded manually from their sources into `datasets/<name>/raw_archive/`; verify against `research/dataset_manifests/archives_checksums.json`. AlexNet (LPIPS) and ResNet-50 weights go to `checkpoints/torch`; Zero-DCE Epoch99 weights from the official repository.
4. **Full run (resumable)**:
   `python research/scripts/run_all_research.py --config research/configs/research_full.yaml --resume`
   For a detached run that survives terminal closure (systemd user service): `bash research/scripts/launch_detached.sh`. Status is written to `experiment_outputs/stage_status.json`, logs to `logs/run_all.log`.
5. **Tests**: `pytest research/tests` (7 tests; also run by the preflight stage). The v0 sources are checked against tag `TASC-v0`.
6. **Report assets**: `python research/scripts/make_qualitative.py` (needs Sentinel-2 data), then `python research/scripts/build_manuscript.py` to regenerate `manuscript/first_draft.tex` and `first_draft.pdf` from `first_draft.md`. A real IEEEtran build: `pdflatex first_draft && bibtex first_draft && pdflatex first_draft` x2 in `research/manuscript/` (the `.tex` has not been compiled with a TeX engine in this environment; the PDF is produced by the WeasyPrint route).
7. Total wall time of the full batch on the reference machine (12 CPU cores, no GPU): about 5.8 h (20,961 s).
