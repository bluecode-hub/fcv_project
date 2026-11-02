"""iSAID-dark (Yao et al., IEEE TGRS 2024) evaluation. Archive folder 'iSAID2' from the DFFN authors' release.

Evaluation sets (no training is done anywhere in this project):
  val        : 66 paired 512x512 crops (clean gt + synthetic low-light 'low')
  highpixel  : 24 scenes x 3 darkness levels (15/20/30), 1080p
The 3755 training pairs are not used (and not extracted). Low-light images are SYNTHETICALLY darkened.
"""
from __future__ import annotations

from pathlib import Path

from . import paths, datasets as DS, experiments as E, runner
from .store import Store


def samples(which: str):
    root = paths.ds("isaid_dark") / "extracted" / "iSAID2"
    if which == "val":
        for g in sorted((root / "val" / "gt").glob("*.png")):
            low = root / "val" / "low" / g.name
            yield dict(name=f"val/{g.name}", source=f"val/{g.name}", group="val", bands=DS.read_bgr(low), gt=DS.read_bgr(g),
                       degradation="isaid-val")
    else:
        hp = root / "iSAID-high-pixel"
        for g in sorted((hp / "gt").glob("*.png")):
            for lvl in ("15", "20", "30"):
                low = hp / "low" / lvl / g.name
                if low.exists():
                    yield dict(name=f"hp/{lvl}/{g.name}", source=f"hp/{g.name}", group=f"hp{lvl}", bands=DS.read_bgr(low),
                               gt=DS.read_bgr(g), degradation=f"isaid-hp{lvl}")


def run(cfg, log):
    root = paths.ds("isaid_dark") / "extracted" / "iSAID2"
    if not (root / "val").exists():
        raise FileNotFoundError(f"iSAID-dark not extracted: {root}")
    store = Store(paths.out_dir("e_isaid_dark") / "results.jsonl")
    names = list(E.rgb_methods("cpu").keys())
    res = {}
    for which in ("val", "highpixel"):
        ok, fail = runner.run(samples(which), "rgb_methods", "metric_paired", store, names,
                              workers=(int(cfg.get("workers", 4)) if which == "val" else int(cfg.get("workers_highres", 2))), log=log)
        res[which] = dict(ok=ok, fail=fail)
    return res
