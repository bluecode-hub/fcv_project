#!/usr/bin/env python
"""Single entry point for the whole research batch.

    python research/scripts/run_all_research.py --config research/configs/research_full.yaml --resume

Stages are idempotent: every result row is appended to a JSONL store keyed by (sample, method), so --resume
skips completed valid work. A stage that cannot run (missing dataset, missing weights) is recorded as
'skipped' with the reason; it never aborts the batch. Status goes to experiment_outputs/stage_status.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import yaml  # noqa: E402

from research.trs import paths, stages, datasets as DS  # noqa: E402
from research.trs.stages import log_to  # noqa: E402


def sh(*a, cwd=REPO):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True).stdout.strip()


def sha256(p, n=1 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while b := f.read(n):
            h.update(b)
    return h.hexdigest()


# ------------------------------------------------------------------ stages
def st_preflight(cfg, log):
    info = paths.check_drive(10)
    info["branch"] = sh("git", "rev-parse", "--abbrev-ref", "HEAD")
    info["commit"] = sh("git", "rev-parse", "HEAD")
    info["v0_tag_commit"] = sh("git", "rev-parse", "TASC-v0^{commit}")
    info["v0_diff_in_tasc"] = sh("git", "diff", "--stat", "TASC-v0", "--", "tasc/*.py")
    assert info["v0_diff_in_tasc"] == "", "frozen TASC-v0 sources were modified"
    assert info["branch"] != "main", "must run on the research branch"
    import torch
    info.update(platform=platform.platform(), python=sys.version.split()[0], torch=torch.__version__,
                cuda=torch.cuda.is_available())
    # unit / equivalence tests
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "research/tests", "-x"], cwd=REPO, capture_output=True, text=True)
    info["tests"] = r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr[-200:]
    assert r.returncode == 0, f"tests failed:\n{r.stdout}"
    # checksums of downloaded archives against manifests (when a manifest exists)
    mdir = paths.RESEARCH / "dataset_manifests"
    bad = []
    for mf in mdir.glob("*_checksums.json"):
        for rel, h in json.load(open(mf)).items():
            p = paths.ROOT / rel
            if p.exists() and sha256(p) != h:
                bad.append(rel)
    assert not bad, f"checksum mismatch: {bad}"
    info["checksum_mismatches"] = bad
    return info


def st_manifests(cfg, log):
    mdir = paths.RESEARCH / "dataset_manifests"
    mdir.mkdir(exist_ok=True)
    out = {}
    if (paths.ds("aid") / "listing.json").exists():
        m = DS.build_aid_manifest(cfg["aid"]["per_class"], 30, cfg["aid"]["val_fraction"], cfg["seed"])
        if m["n"] > 0:
            json.dump(m, open(mdir / "aid_subset.json", "w"), indent=1)
            out["aid"] = dict(n=m["n"], head_train=len(m["head_train"]),
                              test=sum(v == "test" for v in m["split"].values()))
    # validate: no overlap between eval pool and head-training set; val/test disjoint
    if "aid" in out:
        m = json.load(open(mdir / "aid_subset.json"))
        assert not set(m["split"]) & set(m["head_train"]), "head-train leaks into eval"
    from research.trs import s2data
    sc = s2data.list_scenes()
    json.dump([{k: s[k] for k in ("name", "region", "split", "datetime", "sun_az", "sun_el", "cloud_cover", "item_id", "mgrs", "processing_baseline")} for s in sc],
              open(mdir / "sentinel2_scenes.json", "w"), indent=1)
    out["sentinel2_scenes"] = len(sc)
    out["sentinel2_regions_heldout"] = sorted({s["region"] for s in sc if s["split"] == "heldout"})
    return out


def need(path, what):
    if not Path(path).exists():
        raise FileNotFoundError(f"{what} missing: {path}")


def st_landsat(cfg, log):
    need(paths.ds("landsat_original") / "D2_synth/index.json", "Landsat D2")
    return stages.stage_landsat_d2(cfg, log)


def st_s2(cfg, log):
    return stages.stage_sentinel2(cfg, log)


def st_aid(cfg, log):
    need(paths.RESEARCH / "dataset_manifests/aid_subset.json", "AID manifest")
    return stages.stage_aid(cfg, log)


def st_darkrs(cfg, log):
    root = paths.ds("darkrs") / "extracted"
    need(root, "DarkRS")
    return stages.stage_folder_nr("e_darkrs", root, cfg, log, cfg["darkrs"]["max_images"])


def st_exdark(cfg, log):
    root = paths.ds("exdark") / "extracted" / "ExDark"
    need(root, "ExDark")
    return stages.stage_folder_nr("e_exdark", root, cfg, log, cfg["exdark"]["max_images"])


def st_isaid(cfg, log):
    from research.trs import isaid
    return isaid.run(cfg, log)


def st_downstream(cfg, log):
    from research.trs import downstream
    return downstream.run(cfg, log)


def st_eff(cfg, log):
    from research.trs import efficiency
    return efficiency.run(cfg, log)


def st_analysis(cfg, log):
    from research.trs import analysis
    return analysis.run(cfg, log)


def st_reports(cfg, log):
    from research.trs import reports
    return reports.run(cfg, log)


STAGES = dict(preflight=st_preflight, manifests=st_manifests, e_landsat_d2=st_landsat, e_sentinel2=st_s2,
              e_aid=st_aid, e_isaid_dark=st_isaid, e_darkrs=st_darkrs, e_exdark=st_exdark,
              e_downstream=st_downstream, e_efficiency=st_eff, analysis=st_analysis, reports=st_reports)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(paths.RESEARCH / "configs/research_full.yaml"))
    ap.add_argument("--resume", action="store_true", help="skip stages already marked done (rows are always resumable)")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--smoke-only", action="store_true")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config))
    paths.check_drive(10)
    log = log_to("run_all")
    sf = paths.ROOT / "experiment_outputs/stage_status.json"
    status = json.load(open(sf)) if sf.exists() else {}
    t_all = time.time()
    for name in cfg["stages"]:
        if a.only and name not in a.only:
            continue
        if a.resume and status.get(name, {}).get("state") == "done" and name not in ("analysis", "reports", "preflight", "manifests"):
            log(f"[{name}] already done, skipping")
            continue
        log(f"[{name}] start")
        t0 = time.time()
        try:
            res = STAGES[name](cfg, log)
            status[name] = dict(state="done", seconds=round(time.time() - t0, 1), result=res)
        except FileNotFoundError as e:
            status[name] = dict(state="skipped", reason=str(e))
            log(f"[{name}] SKIPPED: {e}")
        except AssertionError as e:
            status[name] = dict(state="failed", reason=f"assertion: {e}")
            log(f"[{name}] FAILED: {e}")
            if name == "preflight":
                json.dump(status, open(sf, "w"), indent=1, default=str)
                sys.exit(2)
        except Exception as e:
            status[name] = dict(state="failed", reason=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-1500:])
            log(f"[{name}] FAILED: {e}")
        json.dump(status, open(sf, "w"), indent=1, default=str)
        if a.smoke_only and name == "preflight":
            break
    log(f"batch finished in {time.time()-t_all:.0f}s")
    json.dump(status, open(sf, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
