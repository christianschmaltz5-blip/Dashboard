#!/bin/bash
# ARC MLS Report — daily runner (6:00 AM via macOS launchd)

PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
REPO=/Users/christianschmaltz/arc-dashboard
LOG=/tmp/arc-mls-report.log

echo "=== $(date) ===" >> "$LOG"

# 1. Pull fresh Paragon listings from inbox → updates js/paragon-listings.js + js/market-data.js
cd "$REPO/agents/mls_report"
$PYTHON parse_paragon_inbox.py >> "$LOG" 2>&1

# 2. Send the weekly market report email
$PYTHON mls_report.py --send >> "$LOG" 2>&1

# 3. Commit and push updated JS files so the website reflects new data
cd "$REPO"
git add js/paragon-listings.js js/market-data.js >> "$LOG" 2>&1
git diff --cached --quiet || git commit -m "Auto-update: MLS listings + market data $(date '+%Y-%m-%d')" >> "$LOG" 2>&1
git push origin main >> "$LOG" 2>&1

echo "Done." >> "$LOG"
