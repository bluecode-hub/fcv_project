"""Scene-level paired statistics: bootstrap CI, Wilcoxon, Holm correction."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon


def unit_table(df, metric, unit_col, method_col="method", pre_unit=None):
    """Mean `metric` per (unit, method). `pre_unit` (e.g. 'source') averages repeats (variants,
    tiles, dates) first so that dependent samples are never counted as independent units."""
    d = df[df["status"] == "ok"].dropna(subset=[metric])
    if pre_unit is not None and pre_unit != unit_col:
        d = d.groupby([pre_unit, unit_col, method_col])[metric].mean().reset_index()
    return d.groupby([unit_col, method_col])[metric].mean().unstack(method_col)


def boot_ci(x, n=10000, seed=0):
    x = np.asarray(x, float)
    if len(x) < 2:
        return (np.nan, np.nan)
    r = np.random.default_rng(seed)
    m = r.choice(x, (n, len(x)), replace=True).mean(1)
    return tuple(np.percentile(m, [2.5, 97.5]))


def holm(p):
    p = np.asarray(p, float)
    order = np.argsort(np.where(np.isnan(p), np.inf, p))
    out = np.full_like(p, np.nan)
    m = int((~np.isnan(p)).sum())
    run = 0.0
    for rank, i in enumerate(order[:m]):
        run = max(run, (m - rank) * p[i])
        out[i] = min(1.0, run)
    return out


def compare(tab: pd.DataFrame, ref: str, others, higher_is_better: bool):
    rows = []
    for o in others:
        if o not in tab or ref not in tab:
            continue
        ok = tab[[ref, o]].dropna()
        if len(ok) < 2:
            rows.append(dict(vs=o, n=len(ok), mean_ref=np.nan, mean_other=np.nan, diff=np.nan, ci_lo=np.nan, ci_hi=np.nan, p=np.nan))
            continue
        d = ok[ref] - ok[o]
        try:
            p = wilcoxon(d).pvalue if (d != 0).any() and len(d) >= 5 else np.nan
        except ValueError:
            p = np.nan
        lo, hi = boot_ci(d.values)
        rows.append(dict(vs=o, n=len(ok), mean_ref=ok[ref].mean(), mean_other=ok[o].mean(), diff=d.mean(),
                         ci_lo=lo, ci_hi=hi, p=p, ref_better_frac=float(((d > 0) if higher_is_better else (d < 0)).mean())))
    out = pd.DataFrame(rows)
    if len(out):
        out["p_holm"] = holm(out["p"].values)
    return out
