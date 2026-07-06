#!/bin/bash
# ARC Buyer Match — daily runner (6:30 AM via macOS launchd, after the 6:00 MLS sync)
# Matches saved buyers against the freshly-synced Paragon listings and drops
# "thought of you" drafts into Kevin's Gmail Drafts. Never sends.

PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
REPO=/Users/christianschmaltz/arc-dashboard
LOG=/tmp/arc-buyer-match.log

echo "=== $(date) ===" >> "$LOG"

# Load the Anthropic key (and any overrides) from a gitignored .env, if present.
set -a
[ -f "$REPO/agents/buyer_match/.env" ] && . "$REPO/agents/buyer_match/.env"
set +a

cd "$REPO/agents/buyer_match"
$PYTHON buyer_match.py >> "$LOG" 2>&1

echo "Done." >> "$LOG"
