# Experiment coverage (generated)

Branch `research/illumination-aware-benchmark-v1`, commit `d9215ad`, frozen baseline tag `TASC-v0` = `297a6d7`.

| Stage | State | Detail |
|---|---|---|
| preflight | done | {'mount': '/run/media/ayaan/New Volume', 'root': '/run/media/ayaan/New Volume/TASC_Research', 'free_gb': 115.7, 'branch': 'research/illumination-aware-benchmark |
| manifests | done | {'aid': {'n': 300, 'head_train': 900, 'test': 210}, 'sentinel2_scenes': 24, 'sentinel2_regions_heldout': ['norway_jotunheimen', 'nz_southern_alps']} |
| e_darkrs | done | {'ok': 1032, 'fail': 0, 'methods': 12} |
| analysis | done | {'d2_fail': 0, 'd2_units': 60, 'aid_fail': 0, 'aid_units': 210, 's2_fail': 0, 's2_regions': ['alps_valais', 'atacama_andes', 'colorado_rockies', 'ladakh', 'norw |
| e_landsat_d2 | done | {'ok': 1680, 'fail': 0, 'methods': 28} |
| e_sentinel2 | done | {'scenes': 24, 'ok': 2088, 'fail': 0} |
| e_aid | done | {'ok': 68, 'fail': 0, 'methods': 17} |
| e_isaid_dark | done | {'val': {'ok': 0, 'fail': 0}, 'highpixel': {'ok': 864, 'fail': 0}} |
| e_exdark | done | {'ok': 4800, 'fail': 0, 'methods': 12} |
| e_downstream | done | {'status': 'ok', 'n_test': 210} |
| e_efficiency | done | {'status': 'ok', 'n': 12} |

## Result stores (rows / failures)

| Store | rows ok | rows failed | samples | methods |
|---|---|---|---|---|
| e_aid | 10710 | 0 | 630 | 17 |
| e_darkrs | 1032 | 0 | 86 | 12 |
| e_downstream | 39 | 0 | 39 | 1 |
| e_exdark | 4800 | 0 | 400 | 12 |
| e_isaid_dark | 1656 | 0 | 138 | 12 |
| e_landsat_d2 | 1680 | 0 | 60 | 28 |
| e_sentinel2 | 6264 | 0 | 216 | 29 |
