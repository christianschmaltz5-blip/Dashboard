#!/bin/bash
# ARC Highway 1416 Development Watch — runs Friday via macOS launchd
cd "$(dirname "$0")"
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 monitor.py >> /tmp/arc-hwy1416-dev-watch.log 2>&1
../update_status.sh hwy1416_dev_watch >> /tmp/arc-hwy1416-dev-watch.log 2>&1
