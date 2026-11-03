"""Spot-check that headline numbers quoted in the Phase 4 manuscript equal the CSVs (tolerance = last printed digit)."""
import sys, pandas as pd
from pathlib import Path
T = Path(__file__).resolve().parents[1] / "tables/phase4"
def sm(f, row, col): return pd.read_csv(T / f, index_col=0).loc[row, col]
def cmp(ds, m, vs, ref="C2_local_image"):
    c = pd.read_csv(T / "comparisons.csv"); r = c[(c.dataset == ds) & (c.metric == m) & (c.vs == vs) & (c.ref == ref)].iloc[0]; return r
checks = [("aid psnr C2", sm("aid_summary.csv", "C2_local_image", "psnr"), 14.86), ("aid psnr v0", sm("aid_summary.csv", "TASC-v0", "psnr"), 11.51),
 ("aid pb", sm("aid_summary.csv", "GlobalGamma-perband", "psnr"), 17.51), ("isaid C2", sm("isaid_summary.csv", "C2_local_image", "psnr"), 11.96),
 ("isaid v0", sm("isaid_summary.csv", "TASC-v0", "psnr"), 9.51), ("d2 C2", sm("d2_summary.csv", "C2_local_image", "psnr"), 11.90),
 ("d2 v0dem", sm("d2_summary.csv", "TASC-v0-DEM", "psnr"), 21.65), ("d2 C2b", sm("d2_summary.csv", "C2b_gated_exposure", "psnr"), 20.23),
 ("s2 lift C2", sm("s2_summary.csv", "C2_local_image", "lift_shadow"), 0.053), ("s2 lift v0", sm("s2_summary.csv", "TASC-v0", "lift_shadow"), 0.164),
 ("s2 equal C3", sm("s2_summary.csv", "C3_local_dem", "equalisation_gain"), -0.038), ("dTASC aid", cmp("aid", "psnr", "TASC-v0")["diff"], 3.35),
 ("d isaid", cmp("isaid", "psnr", "TASC-v0")["diff"], 2.45), ("d d2 vs v0", cmp("d2", "psnr", "TASC-v0")["diff"], -9.53),
 ("aid vs pb", cmp("aid", "psnr", "GlobalGamma-perband")["diff"], -2.64), ("isaid vs zdce", cmp("isaid", "psnr", "Zero-DCE")["diff"], -1.42)]
bad = 0
for n, got, want in checks:
    tol = 0.006 if abs(want) < 1 else 0.006 * 1
    ok = abs(float(got) - want) <= max(tol, 0.0051)
    bad += not ok; print(("ok  " if ok else "BAD "), n, round(float(got), 4), want)
d = pd.read_csv(T / "downstream_accuracy.csv", index_col=0)
for v, k, want in [("C2_local_image", "uniform", .829), ("C2_local_image", "severe", .648), ("TASC-v0", "severe", .343), ("Zero-DCE", "uniform", .857)]:
    ok = abs(d.loc[v, k] - want) < 0.0006; bad += not ok; print(("ok  " if ok else "BAD "), v, k, round(d.loc[v, k], 4), want)
print("mismatches:", bad); sys.exit(1 if bad else 0)
