#!/usr/bin/env python
"""Phase 4 final-evaluation orchestrator (resumable; one instance only; run via scripts/launch_phase4.sh).
Refuses to start unless research/reports/phase4_dev_selection.md exists (selection frozen BEFORE test evaluation)."""
from __future__ import annotations

import argparse, json, sys, time, traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import yaml  # noqa: E402
from research.trs import paths, stages_p4 as P  # noqa: E402
from research.trs.stages import log_to          # noqa: E402
import subprocess  # noqa: E402


def sh(*a):
    return subprocess.run(a, cwd=REPO, capture_output=True, text=True).stdout.strip()


def st_preflight(cfg, log):
    info = paths.check_drive(10)
    sel = REPO / "research/reports/phase4_dev_selection.md"
    assert sel.exists(), "dev selection must be written and committed before test evaluation"
    info["selection_committed"] = sh("git", "log", "-1", "--format=%H", "--", str(sel.relative_to(REPO)))
    assert info["selection_committed"], "phase4_dev_selection.md is not committed"
    info.update(branch=sh("git", "rev-parse", "--abbrev-ref", "HEAD"), commit=sh("git", "rev-parse", "HEAD"))
    assert info["branch"] == "research/tasc-v1-phase4"
    assert sh("git", "diff", "--stat", "TASC-v0", "--", "tasc/*.py") == "", "frozen TASC-v0 modified"
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "research/v1/tests", "research/tests"], cwd=REPO, capture_output=True, text=True)
    info["tests"] = r.stdout.strip().splitlines()[-1]
    assert r.returncode == 0, r.stdout[-800:]
    mem = int([l for l in open("/proc/meminfo") if l.startswith("MemAvailable")][0].split()[1]) // 1024
    info["mem_available_mb"] = mem
    assert mem >= 5000, f"only {mem} MB available"
    return info


def need(p, what):
    if not Path(p).exists():
        raise FileNotFoundError(f"{what} missing: {p}")


STAGES = dict(
    preflight=st_preflight,
    p4_landsat_d2=lambda c, l: (need(paths.ds("landsat_original") / "D2_synth/index.json", "Landsat D2"), P.stage_landsat_d2(c, l))[1],
    p4_sentinel2=P.stage_sentinel2,
    p4_aid=lambda c, l: (need(paths.RESEARCH / "dataset_manifests/aid_subset.json", "AID manifest"), P.stage_aid(c, l))[1],
    p4_isaid_dark=P.stage_isaid,
    p4_darkrs=lambda c, l: P.stage_folder_nr("p4_darkrs", need(paths.ds("darkrs") / "extracted", "DarkRS") or paths.ds("darkrs") / "extracted", c, l, c["darkrs"]["max_images"]),
    p4_exdark=lambda c, l: P.stage_folder_nr("p4_exdark", need(paths.ds("exdark") / "extracted" / "ExDark", "ExDark") or paths.ds("exdark") / "extracted" / "ExDark", c, l, c["exdark"]["max_images"]),
    p4_downstream=P.stage_downstream,
    p4_efficiency=P.stage_efficiency,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(paths.RESEARCH / "configs/phase4_full.yaml"))
    ap.add_argument("--resume", action="store_true"); ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config))
    paths.check_drive(10)
    log = log_to("phase4")
    sf = paths.ROOT / "experiment_outputs/phase4_stage_status.json"
    status = json.load(open(sf)) if sf.exists() else {}
    for name in cfg["stages"]:
        if a.only and name not in a.only:
            continue
        if a.resume and status.get(name, {}).get("state") == "done" and name != "preflight":
            log(f"[{name}] done earlier, skipping"); continue
        log(f"[{name}] start"); t0 = time.time()
        try:
            status[name] = dict(state="done", seconds=round(time.time() - t0, 1), result=STAGES[name](cfg, log))
        except FileNotFoundError as e:
            status[name] = dict(state="skipped", reason=str(e)); log(f"[{name}] SKIPPED: {e}")
        except AssertionError as e:
            status[name] = dict(state="failed", reason=f"assertion: {e}"); log(f"[{name}] FAILED: {e}")
            if name == "preflight":
                json.dump(status, open(sf, "w"), indent=1, default=str); sys.exit(2)
        except Exception as e:
            status[name] = dict(state="failed", reason=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-1500:]); log(f"[{name}] FAILED: {e}")
        json.dump(status, open(sf, "w"), indent=1, default=str)
    log("phase 4 evaluation batch finished")


if __name__ == "__main__":
    main()
