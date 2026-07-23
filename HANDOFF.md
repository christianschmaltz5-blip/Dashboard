# Handoff Checklist — Kevin Andreson Operations Dashboard

For whoever (or whichever Claude) is taking over running this repo.

## 1. Get the code

```bash
git clone https://github.com/christianschmaltz5-blip/Dashboard.git arc-dashboard
cd arc-dashboard
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Requires Python 3.14+.

## 2. Git push access (required, not optional)

Every scheduled job's `run.sh` **auto-commits and pushes to `origin main`** at
the end of its run (see step 4 of `agents/mls_report/run.sh` for the pattern —
all agents follow it). This is not just a read/clone situation:

- The new machine needs **write access to this repo** (or the remote needs to
  be repointed to a fork the new machine can push to — if so, update
  `git remote set-url origin <new-url>` and note the new URL here).
- **Remote is HTTPS, not SSH**: `https://github.com/christianschmaltz5-blip/Dashboard.git`.
  Auth is via a stored git-credential token (no `gh` CLI installed on the
  original machine — a personal access token was used via the credential
  helper), not an SSH key. The new machine needs its own token set up
  (`git config credential.helper` + a PAT with repo write scope, or switch the
  remote to SSH and add a deploy key with write access).
- Confirm with `git remote -v` after cloning that origin points where you
  expect before the first scheduled job fires — a silent push failure just
  means listings quietly stop updating (see `agents/mls_report/health_check.py`,
  runs hourly, for how staleness gets detected).

## 3. Secrets (gitignored — hand these off separately, not via this repo)

| File | Contains |
|---|---|
| `agents/mls_report/config.py` | IMAP app password for `arecblackhills@gmail.com`, price bands/property config |
| `agents/mls_report/.env` | Paragon MLS logins (Black Hills + Mount Rushmore boards) |
| `agents/*/config.py` (others) | Recipient lists, board settings — check each folder |
| Anthropic API key | Needed by zoning/newsletter/dev-watch agents that call Claude |

No venv or `.env`-loading framework is used — each Python script just imports
`config.py` directly from its own folder. Scripts `cd` into their own agent
folder explicitly (see `run.sh` below), so there's no reliance on the caller's
working directory.

## 4. Recreate the schedule (macOS launchd — plists don't come with the repo)

Copy each `.plist` below into `~/Library/LaunchAgents/` on the new machine,
then `launchctl load ~/Library/LaunchAgents/<name>.plist`. Fix the absolute
paths inside (`/Users/christianschmaltz/...` → new machine's path) first.

| Job | Schedule | Script |
|---|---|---|
| `com.arc.mls-report` | Daily 6:00 AM | `agents/mls_report/run.sh` |
| `com.arc.zoning-monitor` | Fridays 7:00 AM | `agents/zoning_monitor/run.sh` |
| `com.arc.box-elder-prospects` | Fridays 7:00 AM | `agents/box_elder_prospects/run.sh` |
| `com.arc.hwy1416-dev-watch` | Fridays 7:15 AM | `agents/hwy1416_dev_watch/run.sh` |
| `com.arc.buyer-match` | Daily 6:30 AM | `agents/buyer_match/run.sh` |
| `com.arc.health-check` | Hourly | `agents/mls_report/health_check.py` |

Not on Mac / going to a Linux host instead: same schedule as cron entries,
same `run.sh` scripts work unchanged (just don't use launchd's plist format).

## 5. Known open issue to inherit

MLS listings are stale as of 2026-07-23 — Paragon's saved-search email alerts
to `arecblackhills@gmail.com` appear to have stopped delivering around July 1.
Pipeline runs fine daily; it just has nothing new to parse. Needs someone with
Paragon Collaboration Center access (both Black Hills and Mount Rushmore MLS
boards) to re-enable/re-save the saved-search auto-email alerts.

## 6. Everything else

See `README.md` in this repo for the full agent list, manual run commands,
and repo layout.
