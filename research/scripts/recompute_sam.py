"""Correction pass: recompute ONLY the spectral metrics (SAM, NDVI/NDWI error, band-ratio deviation; corrected, research/trs/spectral.py) for Landsat D2 and
Sentinel-2.  Methods are re-run (outputs were not stored); the original stores are left untouched.
New stores: experiment_outputs/e_landsat_d2_spectral, e_sentinel2_spectral.  Resumable."""
import multiprocessing as mp
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from research.trs import paths, datasets as DS, experiments as E, runner, s2data, stages  # noqa: E402
from research.trs.store import Store, Timer  # noqa: E402
import numpy as np  # noqa: E402


def _job(args):
    name, wrong_name, threads = args
    import os
    os.environ["OMP_NUM_THREADS"] = str(threads)
    import cv2, torch
    cv2.setNumThreads(threads); torch.set_num_threads(threads)
    sc = s2data.load_scene(name)
    wrong = s2data.load_scene(wrong_name)["dem"] if wrong_name else None
    V = s2data.terrain_variants(sc, wrong)
    M = E.s2_methods("cpu")
    rows = []
    for s in s2data.tiles(sc, V):
        for m, f in M.items():
            try:
                out = np.clip(np.asarray(f(s), np.float32), 0, 1)
                rows.append(dict(sample=s["name"], method=m, group=s["region"], status="ok", **E.metric_s2_sam(out, s)))
            except Exception as e:
                rows.append(dict(sample=s["name"], method=m, group=s["region"], status=f"fail: {type(e).__name__}: {str(e)[:200]}"))
    return name, rows


def main():
    paths.check_drive(10)
    log = stages.log_to("recompute_spectral")
    t0 = time.time()
    st = Store(paths.out_dir("e_landsat_d2_spectral") / "results.jsonl")
    names = list(E.d2_methods("cpu").keys())
    ok, fail = runner.run(DS.d2_samples("test"), "d2_methods", "metric_d2_sam", st, names, workers=4, log=log)
    log(f"landsat d2 sam: {ok} ok / {fail} fail, {time.time()-t0:.0f}s")
    store = Store(paths.out_dir("e_sentinel2_spectral") / "results.jsonl")
    scenes = s2data.list_scenes()
    done = {s for s, _ in store.done}
    todo = []
    for i, m in enumerate(scenes):
        if any(k.startswith(m["name"] + "_r") for k in done):
            continue
        others = [x for x in scenes if x["region"] != m["region"]]
        todo.append((m["name"], others[i % len(others)]["name"] if others else None, 2))   # same wrong-DEM pairing as original
    ctx = mp.get_context("spawn")
    ok = fail = 0
    if todo:
        with ctx.Pool(min(3, len(todo)), maxtasksperchild=1) as pool:
            for name, rows in pool.imap_unordered(_job, todo):
                for r in rows:
                    store.add(**r); ok += r["status"] == "ok"; fail += r["status"] != "ok"
                log(f"  scene {name}: {len(rows)} rows")
    log(f"sentinel2 sam: {ok} ok / {fail} fail; total {time.time()-t0:.0f}s; DONE")


if __name__ == "__main__":
    main()
