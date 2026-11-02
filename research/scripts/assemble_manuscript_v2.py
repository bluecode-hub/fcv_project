"""One-off assembly of the corrected manuscript (v2): fills table rows from the recorded CSVs so that no result is typed
by hand, then writes research/manuscript/first_draft.md.  Source text lives in manuscript/_v2_sections.md (Results..Conclusion)."""
import re
from pathlib import Path

import pandas as pd

RES = Path(__file__).resolve().parents[1]
TAB = RES / "tables"
MAN = RES / "manuscript"


def rows(csv, spec, order):
    """spec: list of (md header, csv col, decimals); order: list of (display name, csv index)."""
    df = pd.read_csv(TAB / csv, index_col=0)
    out = []
    for disp, key in order:
        cells = [disp] + [f"{df.loc[key, c]:.{d}f}" for _, c, d in spec]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def best_bold(lines, col, higher=True, skip=()):
    return lines


def main():
    sec = (MAN / "_v2_sections.md").read_text()
    old = (MAN / "first_draft.md").read_text()
    rm = [("Identity", "Identity"), ("HE", "HE"), ("CLAHE", "CLAHE"), ("AGC", "AGC"), ("AGCWD", "AGCWD"), ("Global gamma", "GlobalGamma"),
          ("Global gamma, per band", "GlobalGamma-perband"), ("Zero-DCE", "Zero-DCE")]
    d2 = rm + [("TASC image-only", "A4_no_dem"), ("TASC-v0 (DEM)", "TASC-v0")]
    sec = sec.replace("D2_ROWS", rows("d2_summary_raw.csv", [("PSNR", "psnr", 2), ("SSIM", "ssim", 3), ("LPIPS", "lpips", 3), ("MAE", "mae_shadow", 3),
                                                              ("NDVI", "ndvi_mae_vs_gt", 3), ("SAM", "sam_vs_gt", 2), ("SAMi", "sam_vs_input", 2)], d2))
    isd = rm + [("2D-gamma", "2D-gamma"), ("TASC-image", "TASC-image")]
    sec = sec.replace("ISAID_ROWS", rows("isaid_summary_raw.csv", [("a", "psnr", 2), ("b", "ssim", 3), ("c", "halo", 3), ("d", "noise_amp", 2)], isd))
    aid = rm + [("2D-gamma", "2D-gamma"), ("TASC-image", "TASC-image"), ("TASC-image, no global exposure", "TASC-image/no-global-exposure"),
                ("TASC-image, per band", "TASC-image/per-band")]
    sec = sec.replace("AID_ROWS", rows("aid_summary_raw.csv", [("a", "psnr", 2), ("b", "ssim", 3), ("c", "lpips", 3), ("d", "bright_clip_new", 3),
                                                                ("e", "halo", 3), ("f", "noise_amp", 2)], aid))
    nr = rm + [("2D-gamma", "2D-gamma"), ("TASC-image", "TASC-image")]
    nrs = [("a", "entropy", 2), ("b", "eme", 2), ("c", "brisque", 1), ("d", "niqe", 2), ("e", "noise_amp", 2)]
    sec = sec.replace("DARKRS_ROWS", rows("darkrs_summary_raw.csv", nrs, nr)).replace("EXDARK_ROWS", rows("exdark_summary_raw.csv", nrs, nr))
    s2 = [("Identity", "Identity"), ("Global gamma", "GlobalGamma"), ("Global gamma, per band", "GlobalGamma-perband"), ("CLAHE", "CLAHE"), ("AGC", "AGC"),
          ("AGCWD", "AGCWD"), ("HE", "HE"), ("Zero-DCE", "Zero-DCE"), ("C-correction", "C-correction"), ("SCS+C", "SCS+C"), ("TASC image-only", "TASC-image"),
          ("TASC-DEM", "TASC-DEM"), ("TASC-DEM, wrong DEM", "TASC-DEM/wrong-DEM"), ("TASC-DEM, shift 1 km", "TASC-DEM/shift1km"),
          ("TASC-DEM, β-only", "TASC-DEM/beta-only"), ("TASC-DEM, per band", "TASC-DEM/per-band")]
    dev = pd.read_csv(TAB / "s2_summary_dev_raw.csv", index_col=0)
    ho = pd.read_csv(TAB / "s2_summary_heldout_raw.csv", index_col=0)
    lines = []
    for disp, key in s2:
        lines.append(f"| {disp} | {dev.loc[key,'lift_shadow']:.3f} | {ho.loc[key,'lift_shadow']:.3f} | {dev.loc[key,'ndvi_mae']:.3f} | {dev.loc[key,'sam']:.2f} | {ho.loc[key,'sam']:.2f} |")
    sec = sec.replace("S2_ROWS", "\n".join(lines))
    a = old.index("## V. Results")
    b = old.index("## Data and Code Availability")
    new = old[:a] + sec.strip() + "\n\n" + old[b:]
    (MAN / "first_draft.md").write_text(new)
    print("assembled; remaining placeholders:", re.findall(r"[A-Z0-9]+_ROWS|SAM_TEXT", new))


if __name__ == "__main__":
    main()
