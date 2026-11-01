"""Append-only, resumable result store (JSON lines on the external drive)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np


def _clean(v):
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.done = set()
        if self.path.exists():
            for line in open(self.path):
                try:
                    r = json.loads(line)
                    self.done.add((r["sample"], r["method"]))
                except Exception:
                    pass          # truncated final line after interruption: ignored, recomputed

    def has(self, sample, method):
        return (sample, method) in self.done

    def add(self, **row):
        row = {k: _clean(v) for k, v in row.items()}
        with open(self.path, "a") as f:
            f.write(json.dumps(row) + "\n")
        self.done.add((row["sample"], row["method"]))


def load_rows(path):
    import pandas as pd
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    return pd.read_json(p, lines=True)


class Timer:
    def __enter__(self):
        self.t = time.perf_counter()
        return self

    def __exit__(self, *a):
        self.dt = time.perf_counter() - self.t
