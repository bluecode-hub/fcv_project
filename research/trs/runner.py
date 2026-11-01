"""Parallel, resumable sample x method runner. Workers build the method set once; the parent writes rows."""
from __future__ import annotations

import multiprocessing as mp
import os
import time
import traceback

import numpy as np

from .store import Store, Timer

_W = {}


def _init(factory_name, device, threads):
    os.environ["OMP_NUM_THREADS"] = str(threads)
    import cv2
    cv2.setNumThreads(threads)
    try:
        import torch
        torch.set_num_threads(threads)
    except Exception:
        pass
    from . import experiments as E
    _W["methods"] = getattr(E, factory_name)(device)
    _W["metrics"] = E


def _work(args):
    s, todo, metric_name = args
    metric = getattr(_W["metrics"], metric_name)
    rows = []
    for m in todo:
        f = _W["methods"][m]
        try:
            with Timer() as t:
                out = np.clip(np.asarray(f(s), np.float32), 0, 1)
            r = metric(out, s)
            mp_ = s["bands"].shape[0] * s["bands"].shape[1] / 1e6
            rows.append(dict(sample=s["name"], method=m, group=s.get("group"), ms_per_mp=t.dt * 1e3 / mp_, status="ok", **r))
        except Exception as e:
            rows.append(dict(sample=s["name"], method=m, group=s.get("group"),
                             status=f"fail: {type(e).__name__}: {str(e)[:200]}"))
    # drop big arrays
    return rows


def run(samples, factory_name, metric_name, store: Store, methods_all, workers=6, device="cpu", log=print,
        only=None):
    """samples: iterable of dicts. methods_all: names to run. Returns (n_ok, n_fail)."""
    def gen():
        for s in samples:
            todo = [m for m in methods_all if not store.has(s["name"], m) and (only is None or m in only)]
            if todo:
                yield (s, todo, metric_name)

    ok = fail = 0
    t0 = time.time()
    if workers <= 1:
        _init(factory_name, device, max(1, os.cpu_count() // 2))
        it = map(_work, gen())
        pool = None
    else:
        ctx = mp.get_context("spawn")
        pool = ctx.Pool(workers, initializer=_init, initargs=(factory_name, device, max(1, os.cpu_count() // workers)))
        it = pool.imap_unordered(_work, gen(), chunksize=1)
    n = 0
    for rows in it:
        for r in rows:
            store.add(**r)
            if r["status"] == "ok":
                ok += 1
            else:
                fail += 1
        n += 1
        if n % 10 == 0:
            log(f"    {n} samples, {ok} ok / {fail} fail, {time.time()-t0:.0f}s")
    if pool:
        pool.close()
        pool.join()
    return ok, fail
