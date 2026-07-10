#!/bin/bash
# ARC Zoning & Planning Monitor — runs Friday at 7:00 AM via macOS launchd
cd "$(dirname "$0")"
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 monitor.py >> /tmp/arc-zoning-monitor.log 2>&1
