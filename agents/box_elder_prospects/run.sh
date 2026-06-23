#!/bin/bash
# ARC Box Elder Prospects — runs Monday, Tuesday, Thursday via macOS launchd
cd "$(dirname "$0")"
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 monitor.py >> /tmp/arc-box-elder-prospects.log 2>&1
