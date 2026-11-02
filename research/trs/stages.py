"""Stage implementations called by scripts/run_all_research.py."""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import time
from pathlib import Path

import numpy as np

from . import paths, datasets as DS, experiments as E, runner, s2data
from .store import Store, Timer


def log_to(name):
    f = open(paths.ROOT / "logs" / f"{name}.log", "a")

    def log(msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        f.write(line + "\n")
        f.flush()
    return log


# ------------------------------------------------------------------ Sentinel-2 (scene-level jobs)
def _s2_job(args):
    name, wrong_name, device, threads, todo_by_tile = args
    os.environ["OMP_NUM_THREADS"] = str(threads)
    import cv2, torch
    cv2.setNumThreads(threads)
    torch.set_num_threads(threads)
    sc = s2data.load_scene(name)
    wrong = s2data.load_scene(wrong_name)["dem"] if wrong_name else None
    V = s2data.terrain_variants(sc, wrong)
    M = E.s2_methods(device)
    rows = []
    for s in s2data.tiles(sc, V):
        for m, f in M.items():
            try:
                with Timer() as t:
                    out = np.clip(np.asarray(f(s), np.float32), 0, 1)
                r = E.metric_s2(out, s)
                rows.append(dict(sample=s["name"], method=m, group=s["region"], status="ok",
                                 ms_per_mp=t.dt * 1e3 / (s["bands"].shape[0] * s["bands"].shape[1] / 1e6), **r))
            except Exception as e:
                rows.append(dict(sample=s["name"], method=m, group=s["region"], status=f"fail: {type(e).__name__}: {str(e)[:200]}"))
    return name, rows


def stage_sentinel2(cfg, log):
    scenes = s2data.list_scenes()
    store = Store(paths.out_dir("e_sentinel2") / "results.jsonl")
    done_scenes = {s for s, _ in store.done}
    todo = []
    for i, m in enumerate(scenes):
        if any(k.startswith(m["name"] + "_r") for k in done_scenes):
            log(f"  skip {m['name']} (done)")
            continue
        others = [x for x in scenes if x["region"] != m["region"]]
        wrong = others[i % len(others)]["name"] if others else None       # DEM of an unrelated region
        todo.append((m["name"], wrong, "cpu", 2, None))
    if not todo:
        return dict(scenes=len(scenes), new=0)
    ctx = mp.get_context("spawn")
    ok = fail = 0
    with ctx.Pool(min(3, len(todo)), maxtasksperchild=1) as pool:
        for name, rows in pool.imap_unordered(_s2_job, todo):
            for r in rows:
                store.add(**r)
                ok += r["status"] == "ok"
                fail += r["status"] != "ok"
            log(f"  scene {name}: {len(rows)} rows")
    return dict(scenes=len(scenes), ok=ok, fail=fail)


# ------------------------------------------------------------------ generic image-only stages
def _par(cfg):
    return int(cfg.get("workers", 4))


def stage_landsat_d2(cfg, log):
    store = Store(paths.out_dir("e_landsat_d2") / "results.jsonl")
    names = list(E.d2_methods("cpu").keys())
    ok, fail = runner.run(DS.d2_samples("test"), "d2_methods", "metric_d2", store, names, workers=_par(cfg), log=log)
    return dict(ok=ok, fail=fail, methods=len(names))


def stage_aid(cfg, log):
    man = json.load(open(paths.RESEARCH / "dataset_manifests/aid_subset.json"))
    store = Store(paths.out_dir("e_aid") / "results.jsonl")
    names = list(E.rgb_abl_methods("cpu").keys())
    samples = DS.aid_samples(man, "test", cfg["aid"]["degradations"], max_side=600)
    ok, fail = runner.run(samples, "rgb_abl_methods", "metric_paired", store, names, workers=_par(cfg), log=log)
    return dict(ok=ok, fail=fail, methods=len(names))


def stage_folder_nr(name, root, cfg, log, max_images, max_side=1024):
    store = Store(paths.out_dir(name) / "results.jsonl")
    names = list(E.rgb_methods("cpu").keys())
    ok, fail = runner.run(DS.folder_samples(root, max_images, max_side), "rgb_methods", "metric_nr", store, names,
                          workers=_par(cfg), log=log)
    return dict(ok=ok, fail=fail, methods=len(names))
