#!/bin/sh
# Launch the whole research batch as a persistent systemd *user* service (own cgroup, survives terminal/Claude exit).
#   research/scripts/launch_detached.sh        # start (no-op if already running)
#   systemctl --user status tasc-research      # state / PID
#   tail -f ~/.local/share/tasc_research/logs/orchestrator.log
#   systemctl --user stop tasc-research        # stop (results stay; rerun to resume)
# ~/.local/share/tasc_research is a space-free symlink to "/run/media/ayaan/New Volume/TASC_Research".
set -e
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
LINK="$HOME/.local/share/tasc_research"
LOG="$LINK/logs/orchestrator.log"
if systemctl --user is-active --quiet tasc-research; then
  echo "tasc-research already running:"; systemctl --user status tasc-research --no-pager | head -5; exit 0
fi
mountpoint -q "/run/media/ayaan/New Volume" || { echo "external drive not mounted"; exit 1; }
systemctl --user reset-failed tasc-research 2>/dev/null || true
systemd-run --user --unit=tasc-research --collect \
  --working-directory="$REPO" \
  -p MemoryHigh=10G -p MemoryMax=12G -p ManagedOOMPreference=avoid \
  -p Restart=on-failure -p RestartSec=60 \
  -p StandardOutput=append:"$LOG" -p StandardError=append:"$LOG" \
  -E OMP_NUM_THREADS=3 -E PYTHONUNBUFFERED=1 \
  "$HOME/venvs/tasc/bin/python" research/scripts/run_all_research.py \
  --config research/configs/research_full.yaml --resume
sleep 3
systemctl --user status tasc-research --no-pager | head -8
