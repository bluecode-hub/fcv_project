#!/bin/sh
# Persistent systemd --user service for the Phase 4 evaluation (own cgroup; survives terminal/Claude exit; resumable).
#   research/scripts/launch_phase4.sh            start (no-op if already running)
#   systemctl --user status tasc-phase4          state
#   journalctl --user -u tasc-phase4 -n 30       recent log
# Safety: one orchestrator only (refuses to start next to tasc-research or tasc-phase4), preflight memory check,
# MemoryHigh/Max below total RAM, systemd-oomd told to avoid this unit last, restarts limited and logged.
set -e
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
MOUNT="${TASC_DRIVE:-/run/media/ayaan/New Volume}"
LOG="$HOME/.local/share/tasc_research/logs/phase4_orchestrator.log"
for u in tasc-research tasc-phase4; do
  systemctl --user is-active --quiet $u && { echo "$u already running; not starting a second orchestrator"; exit 0; }
done
mountpoint -q "$MOUNT" || { echo "external drive not mounted at $MOUNT"; exit 1; }
AVAIL_MB=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
[ "$AVAIL_MB" -ge 6000 ] || { echo "only ${AVAIL_MB} MB RAM available; need >= 6000 (close other apps)"; exit 1; }
mkdir -p "$(dirname "$LOG")"
systemctl --user reset-failed tasc-phase4 2>/dev/null || true
systemd-run --user --unit=tasc-phase4 --collect --working-directory="$REPO" \
  -p MemoryHigh=9G -p MemoryMax=11G -p MemorySwapMax=0 -p ManagedOOMPreference=avoid \
  -p Restart=on-failure -p RestartSec=60 -p StartLimitBurst=5 \
  -p StandardOutput=append:"$LOG" -p StandardError=append:"$LOG" \
  -E OMP_NUM_THREADS=2 -E PYTHONUNBUFFERED=1 \
  "$HOME/venvs/tasc/bin/python" research/scripts/run_phase4_eval.py --config research/configs/phase4_full.yaml --resume
sleep 3; systemctl --user status tasc-phase4 --no-pager | head -8
