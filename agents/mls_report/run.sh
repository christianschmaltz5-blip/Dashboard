#!/bin/bash
# ARC MLS Report — daily runner (6:00 AM via macOS launchd)

PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
REPO=/Users/christianschmaltz/arc-dashboard
LOG=/tmp/arc-mls-report.log

echo "=== $(date) ===" >> "$LOG"

# 1. Pull fresh Paragon listings from inbox → updates js/market-data.js (MLS detail table only;
#    the New MLS Listings page/js was removed 2026-08-12)
cd "$REPO/agents/mls_report"
$PYTHON parse_paragon_inbox.py >> "$LOG" 2>&1

# 2. Send the weekly market report email — Fridays only (date +%u: Mon=1 … Fri=5 … Sun=7).
#    The listings sync above still runs daily; only the emailed report is weekly.
if [ "$(date +%u)" = "5" ]; then
  $PYTHON mls_report.py --send >> "$LOG" 2>&1
else
  echo "Not Friday (weekday $(date +%u)) — skipping weekly market report email." >> "$LOG"
fi

# 3. Record freshness for the dashboard, then commit and push
cd "$REPO"
$PYTHON - "market_report" <<'PYEOF' >> "$LOG" 2>&1
import json, sys, datetime, pathlib
key = sys.argv[1]
path = pathlib.Path("js/agent-status.json")
data = json.loads(path.read_text()) if path.exists() else {}
data[key] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
PYEOF
git add js/market-data.js js/agent-status.json >> "$LOG" 2>&1
git diff --cached --quiet || git commit -m "Auto-update: MLS listings + market data $(date '+%Y-%m-%d')" >> "$LOG" 2>&1
git push origin main >> "$LOG" 2>&1

echo "Done." >> "$LOG"
