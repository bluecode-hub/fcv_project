"""Machine-generated reports (coverage, dataset audit pointers, results summary). Narrative reports are hand-written."""
from __future__ import annotations

import json
import subprocess

import pandas as pd

from . import paths


def _git(*a):
    return subprocess.run(["git", *a], cwd=paths.REPO, capture_output=True, text=True).stdout.strip()


def run(cfg, log):
    od = paths.ROOT / "experiment_outputs"
    st = json.load(open(od / "stage_status.json")) if (od / "stage_status.json").exists() else {}
    rep = paths.RESEARCH / "reports"
    rep.mkdir(exist_ok=True)
    lines = ["# Experiment coverage (generated)", "",
             f"Branch `{_git('rev-parse', '--abbrev-ref', 'HEAD')}`, commit `{_git('rev-parse', '--short', 'HEAD')}`, frozen baseline tag `TASC-v0` = `{_git('rev-parse', '--short', 'TASC-v0^{commit}')}`.", "",
             "| Stage | State | Detail |", "|---|---|---|"]
    for k, v in st.items():
        lines.append(f"| {k} | {v.get('state')} | {str(v.get('reason') or v.get('result'))[:160]} |")
    lines += ["", "## Result stores (rows / failures)", "", "| Store | rows ok | rows failed | samples | methods |", "|---|---|---|---|---|"]
    for p in sorted(od.glob("*/results.jsonl")):
        d = pd.read_json(p, lines=True)
        ok = d[d["status"] == "ok"]
        lines.append(f"| {p.parent.name} | {len(ok)} | {len(d)-len(ok)} | {d['sample'].nunique()} | {d['method'].nunique()} |")
        fails = d[d["status"] != "ok"]
        if len(fails):
            lines.append("")
            lines.append(f"Failures in `{p.parent.name}`:")
            for (m, s), g in fails.groupby(["method", "status"]):
                lines.append(f"- {m}: {s} ({len(g)}x)")
            lines.append("")
    (rep / "experiment_coverage.md").write_text("\n".join(lines) + "\n")
    log("  coverage report written")
    return dict(coverage=str(rep / "experiment_coverage.md"))
