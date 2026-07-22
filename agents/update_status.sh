#!/bin/bash
# Records a UTC "last successful run" timestamp for one agent key in js/agent-status.json
# and pushes it, so the public dashboard can show real freshness instead of a static "Live" label.
# Usage: update_status.sh <agent_key>

REPO=/Users/christianschmaltz/arc-dashboard
KEY="$1"
[ -z "$KEY" ] && exit 1

cd "$REPO" || exit 1

/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 - "$KEY" <<'PYEOF'
import json, sys, datetime, pathlib
key = sys.argv[1]
path = pathlib.Path("js/agent-status.json")
data = json.loads(path.read_text()) if path.exists() else {}
data[key] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
PYEOF

git add js/agent-status.json
git diff --cached --quiet -- js/agent-status.json || git commit -m "Update agent-status: $KEY $(date '+%Y-%m-%d %H:%M')" >/dev/null
git push origin main >/dev/null 2>&1
