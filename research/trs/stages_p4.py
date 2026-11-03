"""Phase 4 stages. Same resumable Store/runner infrastructure as Phase 3, new stores ``p4_*`` on the external drive.
Only TASC-v0 reference rows and TASC-v1 variants are computed; baselines are read from the Phase 3 stores."""
from __future__ import annotations

import json
import multiprocessing as mp
import os

import numpy as np

from . import paths, datasets as DS, experiments as E, runner, s2data
from .store import Store, Timer


def stage_landsat_d2(cfg, log):
    names = list(E.p4_d2_methods("cpu").keys())
    st = Store(paths.out_dir("p4_landsat_d2") / "results.jsonl")
    ok, fail = runner.run(DS.d2_samples("test"), "p4_d2_methods", "metric_d2", st, names, workers=int(cfg["workers"]), log=log)
    st2 = Store(paths.out_dir("p4_landsat_d2_spectral") / "results.jsonl")
    ok2, fail2 = runner.run(DS.d2_samples("test"), "p4_d2_methods", "metric_d2_sam", st2, names, workers=int(cfg["workers"]), log=log)
    return dict(ok=ok, fail=fail, spectral_ok=ok2, spectral_fail=fail2, methods=len(names))


def _s2_job(args):
    name, wrong_name, threads = args
    os.environ["OMP_NUM_THREADS"] = str(threads)
    import cv2, torch
    cv2.setNumThreads(threads); torch.set_num_threads(threads)
    sc = s2data.load_scene(name)
    wrong = s2data.load_scene(wrong_name)["dem"] if wrong_name else None
    V = s2data.terrain_variants(sc, wrong)
    M = E.p4_s2_methods("cpu")
    rows, rows_sam = [], []
    for s in s2data.tiles(sc, V):
        for m, f in M.items():
            try:
                with Timer() as t:
                    out = np.clip(np.asarray(f(s), np.float32), 0, 1)
                mp_ = s["bands"].shape[0] * s["bands"].shape[1] / 1e6
                rows.append(dict(sample=s["name"], method=m, group=s["region"], status="ok", ms_per_mp=t.dt * 1e3 / mp_, **E.metric_s2(out, s)))
                rows_sam.append(dict(sample=s["name"], method=m, group=s["region"], status="ok", **E.metric_s2_sam(out, s)))
            except Exception as e:
                rows.append(dict(sample=s["name"], method=m, group=s["region"], status=f"fail: {type(e).__name__}: {str(e)[:200]}"))
    return name, rows, rows_sam


def stage_sentinel2(cfg, log):
    scenes = s2data.list_scenes()
    store = Store(paths.out_dir("p4_sentinel2") / "results.jsonl")
    store2 = Store(paths.out_dir("p4_sentinel2_spectral") / "results.jsonl")
    done = {s for s, _ in store.done}
    todo = []
    for i, m in enumerate(scenes):
        if any(k.startswith(m["name"] + "_r") for k in done):
            continue
        others = [x for x in scenes if x["region"] != m["region"]]
        todo.append((m["name"], others[i % len(others)]["name"] if others else None, 2))
    ok = fail = 0
    if todo:
        with mp.get_context("spawn").Pool(2, maxtasksperchild=1) as pool:        # <= 2 workers (memory)
            for name, rows, rows_sam in pool.imap_unordered(_s2_job, todo):
                for r in rows:
                    store.add(**r); ok += r["status"] == "ok"; fail += r["status"] != "ok"
                for r in rows_sam:
                    store2.add(**r)
                log(f"  scene {name}: {len(rows)} rows")
    return dict(scenes=len(scenes), ok=ok, fail=fail)


def stage_aid(cfg, log):
    man = json.load(open(paths.RESEARCH / "dataset_manifests/aid_subset.json"))
    store = Store(paths.out_dir("p4_aid") / "results.jsonl")
    names = list(E.p4_rgb_methods("cpu").keys())
    ok, fail = runner.run(DS.aid_samples(man, "test", cfg["aid"]["degradations"], max_side=600), "p4_rgb_methods",
                          "metric_paired", store, names, workers=int(cfg["workers"]), log=log)
    return dict(ok=ok, fail=fail, methods=len(names))


def stage_isaid(cfg, log):
    from . import isaid
    root = paths.ds("isaid_dark") / "extracted" / "iSAID2"
    if not (root / "val").exists():
        raise FileNotFoundError(f"iSAID-dark not extracted: {root}")
    store = Store(paths.out_dir("p4_isaid_dark") / "results.jsonl")
    names = list(E.p4_rgb_methods("cpu").keys())
    res = {}
    for which in ("val", "highpixel"):
        w = int(cfg["workers"]) if which == "val" else int(cfg["workers_highres"])
        res[which] = runner.run(isaid.samples(which), "p4_rgb_methods", "metric_paired", store, names, workers=w, log=log)
    return res


def stage_folder_nr(name, root, cfg, log, max_images):
    store = Store(paths.out_dir(name) / "results.jsonl")
    names = list(E.p4_rgb_methods("cpu").keys())
    ok, fail = runner.run(DS.folder_samples(root, max_images, 1024), "p4_rgb_methods", "metric_nr", store, names,
                          workers=int(cfg["workers_highres"]), log=log)
    return dict(ok=ok, fail=fail)


def stage_downstream(cfg, log, device="cpu"):
    """Same frozen ResNet-50 + logistic-regression head and disjoint protocol as Phase 3 (research/trs/downstream.py)."""
    from . import downstream as DN
    from .downstream import feats, train_head, DS as _DS  # noqa: F401
    import cv2
    man = json.load(open(paths.RESEARCH / "dataset_manifests/aid_subset.json"))
    store = Store(paths.out_dir("p4_downstream") / "results.jsonl")
    clf = train_head(man, log)
    M = E.p4_rgb_methods(device)
    root = paths.ds("aid") / "images"
    test = [k for k, s in sorted(man["split"].items()) if s == "test"]
    for deg in cfg["aid"]["degradations"]:
        for name, f in M.items():
            key = f"{deg}|{name}"
            if store.has(key, "acc"):
                continue
            imgs, y = [], []
            for k in test:
                gt = DS.read_bgr(root / k)
                if max(gt.shape[:2]) > 600:
                    s = 600 / max(gt.shape[:2]); gt = cv2.resize(gt, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
                imgs.append(np.clip(f(dict(bands=DS.degrade(gt, deg, k))), 0, 1).astype(np.float32))
                y.append(k.split("/")[0])
            pred = clf.predict(feats(imgs)); correct = (pred == np.array(y)).astype(float)
            store.add(sample=key, method="acc", variant=name, degradation=deg, status="ok", acc=float(correct.mean()),
                      per_image=json.dumps({k: int(c) for k, c in zip(test, correct)}), n=len(y))
            log(f"  {deg:10s} {name:28s} acc={correct.mean():.3f}")
    return dict(status="ok", n_test=len(test))


EFF_METHODS = ["Identity", "GlobalGamma", "GlobalGamma-perband", "CLAHE", "Zero-DCE", "TASC-v0", "TASC-v0-DEM", "C1_exposure",
               "C2_local_image", "C2b_gated_exposure", "C3_local_dem", "C2/+DCT-detail", "C2/per-band"]


def stage_efficiency(cfg, log):
    """CPU only, 1024x1024 image, one fresh process per method, min of 3 timed runs after a warm-up; peak memory = VmHWM of the
    child (reset at exec — the Phase 3 probe read ru_maxrss, which is inherited from the parent and was identical for all methods)."""
    import glob, subprocess, sys, platform
    img = sorted(glob.glob(str(paths.ds("darkrs") / "extracted" / "**" / "*.jp*g"), recursive=True))
    if not img:
        raise FileNotFoundError("no DarkRS image for the efficiency probe")
    out = paths.out_dir("p4_efficiency")
    rows = []
    for m in EFF_METHODS:
        r = subprocess.run([sys.executable, "-m", "research.trs.stages_p4", m, img[0]], capture_output=True, text=True,
                           cwd=str(paths.REPO), env={"OMP_NUM_THREADS": "4", "PATH": "/usr/bin:/bin", "HOME": "/tmp"})
        try:
            rows.append(json.loads(r.stdout.strip().splitlines()[-1])); log(f"  {m}: {rows[-1]['ms_per_mp']:.0f} ms/MP, peak {rows[-1]['peak_mb']:.0f} MB")
        except Exception:
            rows.append(dict(method=m, status="fail", err=r.stderr[-200:]))
    json.dump(dict(env=dict(platform=platform.platform(), cpu_only=True, threads=4, size="1024x1024"), rows=rows), open(out / "efficiency.json", "w"), indent=1)
    return dict(n=len(rows))


def _hwm_mb():
    for line in open("/proc/self/status"):
        if line.startswith("VmHWM"):
            return int(line.split()[1]) / 1024
    return float("nan")


def _build_one(name):
    from . import methods as MT
    from ..v1.config import CANDIDATES, variant
    from ..v1.method import TASCv1
    from .adapter import run_tasc
    if name == "Identity":
        return lambda s: s["bands"].copy()
    if name == "Zero-DCE":
        return MT.ZeroDCETorch(device="cpu")
    cl = MT.classical_methods()
    if name in cl:
        return cl[name]
    if name == "TASC-v0":
        return lambda s: run_tasc(s["bands"], dict(use_dem=False))
    if name == "TASC-v0-DEM":
        from tasc.method import TASCGamma
        return lambda s: TASCGamma()(s["bands"], s["dem"], s["dx"], s["sun_az"], s["sun_el"])
    c2 = CANDIDATES["C2_local_image"]
    if name == "C3_local_dem":
        return lambda s: TASCv1(variant(CANDIDATES["C3_local_dem"]))(s["bands"], s["dem"], s["dx"], s["sun_az"], s["sun_el"])
    cfgs = {"C1_exposure": CANDIDATES["C1_exposure"], "C2_local_image": c2, "C2/+DCT-detail": variant(c2, detail=True),
            "C2/per-band": variant(c2, shared_gain=False),
            "C2b_gated_exposure": variant(c2, adequate_hi=0.60, adequate_lo=0.40, t_white=0.75, mean_cap=0.6)}
    return lambda s: TASCv1(variant(cfgs[name]))(s["bands"])


def _eff_child(method, img_path):
    import time, cv2
    from scipy.ndimage import gaussian_filter
    im = cv2.resize(cv2.imread(img_path).astype(np.float32) / 255.0, (1024, 1024), interpolation=cv2.INTER_AREA)
    rng = np.random.default_rng(0)
    s = dict(bands=im, dem=(gaussian_filter(rng.normal(0, 1, (1024, 1024)), 40) * 300 + 1500).astype(np.float32), dx=10.0, sun_az=150.0, sun_el=30.0)
    f = _build_one(method)
    base = _hwm_mb()
    f(s)
    ts = []
    for _ in range(3):
        t = time.perf_counter(); f(s); ts.append(time.perf_counter() - t)
    print(json.dumps(dict(method=method, ms_per_mp=1e3 * min(ts) / 1.048576, peak_mb=_hwm_mb(), baseline_mb=base, needs_dem=method in ("C3_local_dem", "TASC-v0-DEM"))))


if __name__ == "__main__":
    import sys
    _eff_child(sys.argv[1], sys.argv[2])
