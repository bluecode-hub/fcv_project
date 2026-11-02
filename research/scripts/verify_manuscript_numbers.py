"""Audit: every number in the manuscript tables must equal the value in the recorded CSV summaries
(research/tables/*_raw.csv, produced by trs/analysis.py from the JSONL stores), and the key numbers quoted in the text
must appear in the corresponding comparison CSVs.  Exit status != 0 and a printed list on any mismatch.

    python research/scripts/verify_manuscript_numbers.py
"""
import re
import sys
from pathlib import Path

import pandas as pd

RES = Path(__file__).resolve().parents[1]
MD = (RES / "manuscript" / "first_draft.md").read_text()
TAB = RES / "tables"

NAMES = {"Identity": "Identity", "HE": "HE", "CLAHE": "CLAHE", "AGC": "AGC", "AGCWD": "AGCWD", "Global gamma": "GlobalGamma",
         "Global gamma, per band": "GlobalGamma-perband", "Zero-DCE": "Zero-DCE", "TASC image-only": "TASC-image",
         "TASC-DEM": "TASC-DEM", "C-correction": "C-correction", "SCS+C": "SCS+C", "2D-gamma": "2D-gamma",
         "TASC-DEM, wrong DEM": "TASC-DEM/wrong-DEM", "TASC-DEM, shift 1 km": "TASC-DEM/shift1km",
         "TASC-DEM, β-only": "TASC-DEM/beta-only", "TASC-DEM, per band": "TASC-DEM/per-band",
         "TASC-image, no global exposure": "TASC-image/no-global-exposure", "TASC-image, per band": "TASC-image/per-band",
         "TASC-image": "TASC-image", "TASC-v0 (DEM)": "TASC-v0"}


def md_table(label):
    m = re.search(r"\{#" + re.escape(label) + r"\}\s*\n\n((?:\|.*\n?)+)", MD)
    assert m, f"table {label} not found"
    rows = [[c.strip().replace("**", "") for c in r.strip().strip("|").split("|")] for r in m.group(1).strip().splitlines()]
    return rows[0], [r for i, r in enumerate(rows) if i not in (0, 1)]


def num(s):
    s = s.replace("−", "-").replace("±", "").strip()
    return float(s)


bad, checked = [], 0


def check(label, csv, cols, index_col=0, rowmap=NAMES):
    """cols: {md column name: (csv column or (colA, colB) for 'a / b' cells, decimals)}"""
    global checked
    df = pd.read_csv(TAB / csv, index_col=index_col)
    head, rows = md_table(label)
    for r in rows:
        meth = rowmap.get(r[0])
        if meth is None or meth not in df.index:
            bad.append(f"{label}: row '{r[0]}' has no CSV counterpart")
            continue
        for cname, (ccol, dec) in cols.items():
            cell = r[head.index(cname)]
            ccols = ccol if isinstance(ccol, tuple) else (ccol,)
            vals = cell.split(" / ")
            if len(vals) != len(ccols):
                bad.append(f"{label}/{r[0]}/{cname}: cell '{cell}' does not match {len(ccols)} CSV columns")
                continue
            for v, cc in zip(vals, ccols):
                want = df.loc[meth, cc]
                checked += 1
                if abs(num(v) - round(float(want), dec)) > 10 ** (-dec) * 0.51:
                    bad.append(f"{label}/{r[0]}/{cname}: md {v} vs csv {float(want):.{dec + 1}f} ({csv}:{cc})")


def claim(csv, filt, col, value, dec, label):
    """A number quoted in the running text/abstract must equal the recorded CSV value."""
    global checked
    df = pd.read_csv(TAB / csv)
    for k, v in filt.items():
        df = df[df[k] == v]
    assert len(df) == 1, (label, csv, filt, len(df))
    checked += 1
    got = round(float(df.iloc[0][col]), dec)
    if abs(got - value) > 10 ** (-dec) * 0.51:
        bad.append(f"text claim {label}: md {value} vs csv {got} ({csv} {filt} {col})")


def text_claims():
    c = claim
    c("d2_vs_tascv0.csv", {"metric": "psnr", "vs": "GlobalGamma"}, "diff", 2.43, 2, "D2 +2.43 dB vs global gamma")
    c("d2_vs_tascv0.csv", {"metric": "psnr", "vs": "Zero-DCE"}, "diff", 4.76, 2, "D2 +4.76 dB vs Zero-DCE")
    c("d2_vs_tascv0.csv", {"metric": "psnr", "vs": "A0_global_gamma_dct"}, "diff", 1.37, 2, "D2 vs A0")
    c("d2_vs_tascv0.csv", {"metric": "psnr", "vs": "A4_no_dem"}, "diff", 0.22, 2, "D2 DEM vs image-only")
    c("d2_vs_tascv0.csv", {"metric": "psnr", "vs": "A4_no_dem"}, "ci_lo", 0.16, 2, "D2 DEM CI lo")
    c("d2_vs_tascv0.csv", {"metric": "mae_shadow", "vs": "A4_no_dem"}, "diff", -0.018, 3, "D2 shadow MAE diff")
    c("d2_vs_tascv0.csv", {"metric": "psnr", "vs": "TASC-DEM/beta-only"}, "diff", 1.86, 2, "beta-only")
    c("d2_vs_tascv0.csv", {"metric": "psnr", "vs": "TASC-DEM/flipped-DEM"}, "diff", 1.20, 2, "flipped DEM")
    c("d2_vs_tascv0.csv", {"metric": "psnr", "vs": "TASC-DEM/el-7"}, "diff", -0.80, 2, "el-7")
    c("d2_vs_tascv0.csv", {"metric": "psnr", "vs": "A5_full_per_band"}, "diff", 6.40, 2, "per-band A5")
    c("d2_vs_tascv0_variant_level_dependent.csv", {"metric": "psnr", "vs": "A4_no_dem"}, "ci_lo", -0.02, 2, "D2 variant-level CI lo")
    c("aid_vs_tasc_image.csv", {"metric": "psnr", "vs": "Identity"}, "diff", 1.19, 2, "AID vs identity")
    c("aid_vs_tasc_image.csv", {"metric": "psnr", "vs": "GlobalGamma"}, "diff", -4.15, 2, "AID vs global gamma")
    c("aid_vs_tasc_image.csv", {"metric": "psnr", "vs": "Zero-DCE"}, "diff", -4.94, 2, "AID vs Zero-DCE")
    c("aid_vs_tasc_image.csv", {"metric": "psnr", "vs": "GlobalGamma-perband"}, "diff", -5.99, 2, "AID vs per-band global gamma")
    c("aid_vs_tasc_image.csv", {"metric": "psnr", "vs": "CLAHE"}, "diff", -2.15, 2, "AID vs CLAHE")
    c("isaid_vs_tasc_image.csv", {"metric": "psnr", "vs": "Identity"}, "diff", -2.26, 2, "iSAID vs identity")
    c("isaid_vs_tasc_image.csv", {"metric": "psnr", "vs": "Zero-DCE"}, "diff", -3.87, 2, "iSAID vs Zero-DCE")
    c("isaid_vs_tasc_image.csv", {"metric": "psnr", "vs": "GlobalGamma-perband"}, "diff", -4.89, 2, "iSAID vs per-band")
    c("darkrs_vs_tasc_image.csv", {"metric": "entropy", "vs": "Identity"}, "diff", -0.42, 2, "DarkRS entropy")
    c("darkrs_vs_tasc_image.csv", {"metric": "brisque", "vs": "Identity"}, "diff", 6.14, 2, "DarkRS BRISQUE")
    c("exdark_vs_tasc_image.csv", {"metric": "niqe", "vs": "Identity"}, "diff", -0.56, 2, "ExDark NIQE")
    c("s2_vs_tasc_dem_dev.csv", {"metric": "lift_shadow", "vs": "TASC-image"}, "diff", 0.025, 3, "S2 dev lift diff")
    c("s2_vs_tasc_dem_all.csv", {"metric": "lift_shadow", "vs": "TASC-image"}, "diff", 0.034, 3, "S2 all lift diff")
    c("downstream_vs_identity.csv", {"degradation": "uniform", "variant": "TASC-image"}, "diff_vs_identity", -0.200, 3, "E7 uniform")
    c("downstream_vs_identity.csv", {"degradation": "nonuniform", "variant": "TASC-image"}, "diff_vs_identity", -0.148, 3, "E7 nonuniform")
    c("downstream_vs_identity.csv", {"degradation": "severe", "variant": "TASC-image"}, "diff_vs_identity", -0.238, 3, "E7 severe")


def main():
    global checked
    check("tab:d2", "d2_summary_raw.csv", {"PSNR ↑": ("psnr", 2), "SSIM ↑": ("ssim", 3), "LPIPS ↓": ("lpips", 3),
                                           "MAE shadow ↓": ("mae_shadow", 3), "NDVI err ↓": ("ndvi_mae_vs_gt", 3),
                                           "SAM vs reference (°) ↓": ("sam_vs_gt", 2), "SAM vs input (°)": ("sam_vs_input", 2)},
          rowmap={**NAMES, "TASC image-only": "A4_no_dem"})
    check("tab:aid", "aid_summary_raw.csv", {"PSNR": ("psnr", 2), "SSIM": ("ssim", 3), "LPIPS": ("lpips", 3),
                                             "New clipped bright": ("bright_clip_new", 3), "Halo": ("halo", 3), "Noise amp.": ("noise_amp", 2)})
    check("tab:isaid", "isaid_summary_raw.csv", {"PSNR": ("psnr", 2), "SSIM": ("ssim", 3), "Halo": ("halo", 3), "Noise amp.": ("noise_amp", 2)})
    for lab, csv in (("tab:darkrs", "darkrs_summary_raw.csv"), ("tab:exdark", "exdark_summary_raw.csv")):
        check(lab, csv, {"Entropy": ("entropy", 2), "EME": ("eme", 2), "BRISQUE": ("brisque", 1), "NIQE": ("niqe", 2),
                         "Noise amp.": ("noise_amp", 2)})
    s2d, s2h = "s2_summary_dev_raw.csv", "s2_summary_heldout_raw.csv"
    check("tab:s2", s2d, {"Lift dev": ("lift_shadow", 3), "NDVI err dev": ("ndvi_mae", 3), "SAM dev (°)": ("sam", 2)})
    check("tab:s2", s2h, {"Lift HO": ("lift_shadow", 3), "SAM HO (°)": ("sam", 2)})
    # E7
    acc = pd.read_csv(TAB / "downstream_accuracy.csv", index_col=0)
    head, rows = md_table("tab:e7")
    for r in rows:
        meth = {"Clean reference": "Clean-reference", "Global gamma": "GlobalGamma", "Global gamma, per band": "GlobalGamma-perband"}.get(r[0], r[0])
        for c, deg in (("Uniform", "uniform"), ("Non-uniform", "nonuniform"), ("Severe", "severe")):
            checked += 1
            if abs(float(r[head.index(c)]) - round(acc.loc[meth, deg], 3)) > 0.0006:
                bad.append(f"tab:e7/{r[0]}/{c}")
    text_claims()
    print(f"checked {checked} table cells; mismatches: {len(bad)}")
    for b in bad:
        print("  MISMATCH", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
