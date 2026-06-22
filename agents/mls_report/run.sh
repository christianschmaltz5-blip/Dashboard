#!/bin/bash
# ARC MLS Report — weekly runner
# Runs every Monday at 6:00 AM via macOS launchd
# Once Gmail App Password is added to config.py, change --preview to --send

cd "$(dirname "$0")"
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 mls_report.py --send >> /tmp/arc-mls-report.log 2>&1
