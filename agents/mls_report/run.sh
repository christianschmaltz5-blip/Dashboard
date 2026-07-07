#!/bin/bash
# ARC MLS Report — daily runner (6:00 AM via macOS launchd)

PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
REPO=/Users/christianschmaltz/arc-dashboard
LOG=/tmp/arc-mls-report.log

echo "=== $(date) ===" >> "$LOG"

# 1. Pull fresh Paragon listings from inbox → updates js/paragon-listings.js + js/market-data.js
cd "$REPO/agents/mls_report"
$PYTHON parse_paragon_inbox.py >> "$LOG" 2>&1

# 2. Send the weekly market report email — Fridays only (date +%u: Mon=1 … Fri=5 … Sun=7).
#    The listings sync above still runs daily; only the emailed report is weekly.
if [ "$(date +%u)" = "5" ]; then
  $PYTHON mls_report.py --send >> "$LOG" 2>&1
else
  echo "Not Friday (weekday $(date +%u)) — skipping weekly market report email." >> "$LOG"
fi

# 3. Bump cache-busting version in paragon-listings.html so browsers always fetch fresh JS
VER=$(date '+%Y%m%d')
sed -i '' "s/paragon-listings\.js?v=[0-9]*/paragon-listings.js?v=$VER/g" "$REPO/pages/paragon-listings.html"
sed -i '' "s/market-data\.js?v=[0-9]*/market-data.js?v=$VER/g" "$REPO/pages/paragon-listings.html"

# 4. Commit and push
cd "$REPO"
git add js/paragon-listings.js js/market-data.js pages/paragon-listings.html img/listings/ >> "$LOG" 2>&1
git diff --cached --quiet || git commit -m "Auto-update: MLS listings + market data $(date '+%Y-%m-%d')" >> "$LOG" 2>&1
git push origin main >> "$LOG" 2>&1

echo "Done." >> "$LOG"
