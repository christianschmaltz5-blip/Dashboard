#!/usr/bin/env python3
"""
Hourly health check for the ARC Dashboard.

Checks:
  1. Photo files — every listing with a photo_url has its .jpg on disk
  2. Photo render  — Playwright loads paragon-listings.html and counts
                     images that actually rendered vs. placeholders
  3. Data freshness — paragon-listings.js was generated within 48 hours
  4. Duplicate photos — no two listings share the same image file

Auto-fix: if photos are missing or stale, re-runs parse_paragon_inbox.py
          then commits + pushes any new files.
"""

import json, os, re, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

REPO        = Path(__file__).resolve().parents[2]
JS_FILE     = REPO / "js" / "paragon-listings.js"
IMG_DIR     = REPO / "img" / "listings"
PAGE_URL    = "https://christianschmaltz5-blip.github.io/Dashboard/pages/paragon-listings.html"
PYTHON      = sys.executable
PARSER      = Path(__file__).parent / "parse_paragon_inbox.py"
LOG_FILE    = Path("/tmp/arc-health-check.log")
STALE_HOURS = 48   # re-fetch if data older than this


# ── helpers ───────────────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def load_listings():
    raw = JS_FILE.read_text()
    m = re.search(r"window\.PARAGON_LISTINGS\s*=\s*(\{[\s\S]*?\});", raw)
    if not m:
        return None, None
    data = json.loads(m.group(1))
    return data.get("listings", []), data.get("generated")

def data_age_hours(generated_str):
    if not generated_str:
        return 9999
    formats = [
        "%B %d, %Y at %I:%M %p",   # "June 30, 2026 at 07:30 PM"
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(generated_str.strip(), fmt)
            return (datetime.now() - dt).total_seconds() / 3600
        except ValueError:
            continue
    return 9999


# ── check 1: photo files on disk ─────────────────────────────────────────────

def check_photo_files(listings):
    missing, present = [], []
    seen_paths = {}
    duplicates = []

    for l in listings:
        url = l.get("photo_url") or ""
        if not url or "../img" not in url:
            missing.append(l["mls_num"])
            continue
        fname = url.replace("../img/listings/", "")
        path  = IMG_DIR / fname
        if path.exists():
            present.append(l["mls_num"])
            if fname in seen_paths:
                duplicates.append((l["mls_num"], seen_paths[fname], fname))
            else:
                seen_paths[fname] = l["mls_num"]
        else:
            missing.append(l["mls_num"])

    return present, missing, duplicates


# ── check 2: live render via Playwright ──────────────────────────────────────

def check_render():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("  ⚠  Playwright not available — skipping render check")
        return None, None

    rendered = placeholder = 0
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page    = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(PAGE_URL, wait_until="networkidle", timeout=30000)
            time.sleep(3)

            results = page.evaluate("""() => {
                const imgs = [...document.querySelectorAll('.card-photo img')];
                let rendered = 0, placeholder = 0;
                imgs.forEach(img => {
                    if (img.naturalWidth > 0 && img.style.display !== 'none') rendered++;
                    else placeholder++;
                });
                const allPlaceholders = document.querySelectorAll('.card-photo .placeholder');
                allPlaceholders.forEach(p => {
                    if (p.style.display !== 'none') placeholder++;
                });
                return { rendered, placeholder };
            }""")
            rendered    = results["rendered"]
            placeholder = results["placeholder"]
            browser.close()
    except Exception as e:
        log(f"  ⚠  Render check failed: {e}")
        return None, None

    return rendered, placeholder


# ── check 3: fact-check listing data ─────────────────────────────────────────

def fact_check(listings):
    issues = []
    for l in listings:
        if not l.get("mls_num"):
            issues.append(f"listing missing mls_num: {l.get('address','?')}")
        if not l.get("price") or l["price"] <= 0:
            issues.append(f"MLS {l.get('mls_num','?')} has invalid price: {l.get('price')}")
        if not l.get("address"):
            issues.append(f"MLS {l.get('mls_num','?')} missing address")
        if not l.get("alert_date"):
            issues.append(f"MLS {l.get('mls_num','?')} missing alert_date")
    return issues


# ── auto-fix: re-run parser ───────────────────────────────────────────────────

def run_parser():
    log("  → Running parse_paragon_inbox.py to fix missing photos/data...")
    result = subprocess.run(
        [PYTHON, str(PARSER)],
        cwd=str(PARSER.parent),
        capture_output=True, text=True, timeout=600
    )
    if result.returncode != 0:
        log(f"  ✗ Parser failed:\n{result.stderr[-500:]}")
        return False
    log(f"  ✓ Parser done: {result.stdout.splitlines()[-1] if result.stdout else 'ok'}")
    return True

def commit_and_push(reason):
    log(f"  → Committing: {reason}")
    cmds = [
        ["git", "add", "js/paragon-listings.js", "js/market-data.js",
         "pages/paragon-listings.html", "img/listings/"],
        ["git", "diff", "--cached", "--quiet"],   # exits 1 if staged changes exist
    ]
    subprocess.run(cmds[0], cwd=str(REPO))
    diff = subprocess.run(cmds[1], cwd=str(REPO))
    if diff.returncode == 0:
        log("  → Nothing new to commit")
        return

    msg = f"Auto health-check fix: {reason} ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
    subprocess.run(["git", "commit", "-m", msg], cwd=str(REPO))

    # Bump cache-bust version
    today = datetime.now().strftime("%Y%m%d")
    subprocess.run([
        "sed", "-i", "", f"s/paragon-listings\\.js?v=[0-9a-z]*/paragon-listings.js?v={today}h/g",
        str(REPO / "pages" / "paragon-listings.html")
    ])
    subprocess.run(["git", "add", "pages/paragon-listings.html"], cwd=str(REPO))
    subprocess.run(["git", "commit", "--amend", "--no-edit"], cwd=str(REPO))
    subprocess.run(["git", "push", "origin", "main"], cwd=str(REPO))
    log("  ✓ Pushed to GitHub Pages")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    log("=" * 60)
    log("ARC Dashboard health check starting")

    listings, generated = load_listings()
    if not listings:
        log("✗ Could not parse paragon-listings.js — aborting")
        return

    total = len(listings)
    log(f"Listings loaded: {total}  |  generated: {generated or 'unknown'}")

    # 1. Data freshness
    age = data_age_hours(generated)
    if age > STALE_HOURS:
        log(f"✗ Data is {age:.1f}h old (limit {STALE_HOURS}h) — triggering re-fetch")
        if run_parser():
            commit_and_push("stale data re-fetched")
    else:
        log(f"✓ Data freshness OK ({age:.1f}h old)")

    # 2. Photo files on disk
    present, missing, dupes = check_photo_files(listings)
    log(f"Photos on disk: {len(present)}/{total} present, {len(missing)} missing")
    if missing:
        log(f"  Missing MLS: {', '.join(missing[:10])}{'...' if len(missing)>10 else ''}")
    if dupes:
        log(f"✗ Duplicate photos detected: {dupes}")
        if run_parser():
            commit_and_push("duplicate/missing photos fixed")
    elif missing and len(missing) > 1:
        log("✗ Multiple photos missing — triggering re-fetch")
        if run_parser():
            commit_and_push("missing photos re-fetched")
    else:
        log("✓ Photo files OK")

    # 3. Live render check
    log("Checking live render...")
    rendered, placeholder = check_render()
    if rendered is not None:
        log(f"  Rendered: {rendered} photos  |  Placeholders: {placeholder}")
        if placeholder > 5:
            log(f"⚠  {placeholder} placeholders on live page — may need cache-bust")
        else:
            log("✓ Render OK")

    # 4. Fact-check listing data
    issues = fact_check(listings)
    if issues:
        log(f"⚠  Data issues found ({len(issues)}):")
        for issue in issues[:10]:
            log(f"     {issue}")
    else:
        log(f"✓ All {total} listings pass data validation")

    log("Health check complete")
    log("=" * 60)


if __name__ == "__main__":
    main()
