"""Aggregate a dev CSV per source image, paired bootstrap CIs, gates G1-G3 (pre-registered)."""
import sys
import numpy as np, pandas as pd

def boot(d, n=10000, seed=0):
    rng = np.random.default_rng(seed); d = np.asarray(d); d = d[np.isfinite(d)]
    idx = rng.integers(0, len(d), (n, len(d)))
    m = d[idx].mean(1)
    return d.mean(), np.percentile(m, 2.5), np.percentile(m, 97.5)

def main(csv, out_md=None):
    df = pd.read_csv(csv); df = df[df.status == "ok"]
    cols = [c for c in ["psnr", "ssim", "lpips", "psnr_y", "ssim_y", "mae_dark_in", "bright_clip_new", "halo", "noise_amp", "sec"] if c in df]
    per = df.groupby(["source", "method"])[cols].mean().reset_index()      # unit = source image
    piv = {c: per.pivot(index="source", columns="method", values=c) for c in cols}
    lines = [f"n source images = {piv['psnr'].shape[0]}; unit = source image (3 degradations averaged)\n",
             "| method | PSNR | SSIM | LPIPS | PSNR-Y | SSIM-Y | clip | halo | noise | ΔPSNR vs v0 [95% CI] | ΔSSIM vs v0 [CI] |", "|---|" + "---|" * 10]
    for m in piv["psnr"].columns:
        g = lambda c: piv[c][m].mean() if c in piv else float("nan")
        dp = boot(piv["psnr"][m] - piv["psnr"]["TASC-v0"]); ds = boot(piv["ssim"][m] - piv["ssim"]["TASC-v0"])
        lines.append(f"| {m} | {g('psnr'):.2f} | {g('ssim'):.3f} | {g('lpips'):.3f} | {g('psnr_y'):.2f} | {g('ssim_y'):.3f} | {g('bright_clip_new'):.3f} | {g('halo'):.3f} | {g('noise_amp'):.2f} | {dp[0]:+.2f} [{dp[1]:+.2f},{dp[2]:+.2f}] | {ds[0]:+.3f} [{ds[1]:+.3f},{ds[2]:+.3f}] |")
    txt = "\n".join(lines)
    # gates for each v1 candidate
    gates = ["\n\nGates (G1 PSNR>=v0+2 dB, CI>0, and >= Identity; G2 SSIM>=v0+0.03, LPIPS CI upper<=+0.01; G3 clip<=v0+0.005, halo<=1.25*v0, noise<=v0+0.05)"]
    for m in [c for c in piv["psnr"].columns if c.startswith("C")]:
        p = piv["psnr"]; s = piv["ssim"]
        d = boot(p[m] - p["TASC-v0"]); di = boot(p[m] - p["Identity"])
        g1 = d[0] >= 2.0 and d[1] > 0 and p[m].mean() >= p["Identity"].mean()
        g2 = (s[m] - s["TASC-v0"]).mean() >= 0.03
        if "lpips" in piv and piv["lpips"][m].notna().all():
            g2 = g2 and boot(piv["lpips"][m] - piv["lpips"]["TASC-v0"])[2] <= 0.01
        v0 = {c: piv[c]["TASC-v0"].mean() for c in cols}
        g3 = piv["bright_clip_new"][m].mean() <= v0["bright_clip_new"] + 0.005 and piv["halo"][m].mean() <= 1.25 * v0["halo"] and piv["noise_amp"][m].mean() <= v0["noise_amp"] + 0.05
        gates.append(f"{m}: G1={g1} (Δ={d[0]:+.2f} dB; vs Identity {di[0]:+.2f}) G2={g2} G3={g3}")
    txt += "\n".join(gates)
    print(txt)
    if out_md: open(out_md, "w").write(txt)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
