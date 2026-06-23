"""
Box Elder Prospects Agent — Kevin Andreson
Watches Box Elder, SD Planning & Zoning (primary) and Pennington County
Planning hearing schedules (secondary) for page changes, and emails an
alert only when something changes. Intended to run Mon/Tue/Thu via run.sh.

Run:  python3 monitor.py            <- checks sources, emails on change
      python3 monitor.py --no-email <- checks sources, prints result, no email
"""

import requests
import hashlib
import html as html_lib
import json
import os
import re
import smtplib
import sys
import difflib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

from config import FROM_EMAIL, TO_EMAIL, GMAIL_APP_PASSWORD, SOURCES, STATE_FILE

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), STATE_FILE)
MAX_DIFF_LINES = 40

SCRIPT_STYLE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
BLOCK_BREAK  = re.compile(r"</?(div|p|li|tr|td|th|h[1-6]|br|ul|ol|table)[^>]*>", re.I)
TAG          = re.compile(r"<[^>]+>")


def fetch(url):
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (ARC Box Elder Prospects monitor)"}, timeout=20)
    r.raise_for_status()
    return r.text


def extract_text_lines(raw_html):
    # Strip script/style blocks entirely (noise — analytics IDs, inline JS),
    # then turn block-level tags into line breaks so the result reads like
    # actual page text instead of one giant run-on line.
    text = SCRIPT_STYLE.sub(" ", raw_html)
    text = BLOCK_BREAK.sub("\n", text)
    text = TAG.sub("", text)
    text = html_lib.unescape(text)
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def content_hash(lines):
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def diff_lines(old_lines, new_lines):
    """Only the actual added/removed text, in order — not the unchanged context."""
    return [d for d in difflib.ndiff(old_lines, new_lines) if d.startswith(("+ ", "- "))]


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def send_email(changed_sources):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Box Elder Prospects — Activity Detected — {datetime.now().strftime('%B %d, %Y')}"
    msg["From"] = FROM_EMAIL
    msg["To"]   = TO_EMAIL

    badge = ("display:inline-block;font-size:9px;font-weight:700;letter-spacing:0.05em;"
             "text-transform:uppercase;padding:2px 7px;border-radius:3px;margin-right:10px;"
             "font-family:Arial,sans-serif;")
    new_badge     = badge + "background:#e0e7ff;color:#3730a3;"
    removed_badge = badge + "background:#f1f5f9;color:#64748b;"
    row = "padding:8px 0;border-bottom:1px solid #edf2f7;font-size:13px;color:#1a202c;font-family:Arial,sans-serif;"

    blocks = ""
    for s in changed_sources:
        diff = s["diff"]
        shown, truncated = diff[:MAX_DIFF_LINES], len(diff) > MAX_DIFF_LINES

        rows = ""
        for line in shown:
            text = line[2:]
            label = f"<span style='{new_badge}'>New</span>" if line.startswith("+ ") else f"<span style='{removed_badge}'>Removed</span>"
            rows += f"<div style='{row}'>{label}{text}</div>"
        if not rows:
            rows = "<div style='padding:8px 0;color:#a0aec0;font-size:13px;font-family:Arial,sans-serif;'>Page changed, but no readable text difference was found — likely a layout or script-only change.</div>"
        elif truncated:
            rows += f"<div style='padding:8px 0;color:#a0aec0;font-size:12px;font-family:Arial,sans-serif;'>...and {len(diff) - MAX_DIFF_LINES} more changed line(s). Open the link below for the full page.</div>"

        blocks += f"""
        <div style="margin-bottom:20px;border:1px solid #e2e8f0;border-radius:10px;padding:20px 22px;">
          <div style="font-size:14px;font-weight:700;color:#0f2942;font-family:Arial,sans-serif;">{s['name']}</div>
          <div style="font-size:10px;font-weight:700;color:#a0aec0;text-transform:uppercase;
            letter-spacing:0.08em;margin:3px 0 14px;font-family:Arial,sans-serif;">{s['role']} source</div>
          {rows}
          <a href="{s['url']}" style="display:inline-block;margin-top:14px;font-size:12px;
            color:#1d7eea;text-decoration:none;font-weight:600;font-family:Arial,sans-serif;">View source page &rarr;</a>
        </div>"""

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;">
      <div style="background:#0f2942;border-radius:12px 12px 0 0;padding:28px 32px 24px;">
        <div style="color:#7fb3e0;font-size:11px;font-weight:700;letter-spacing:0.08em;
          text-transform:uppercase;margin-bottom:6px;">Planning &amp; Zoning Alert</div>
        <div style="color:#fff;font-size:22px;font-weight:800;line-height:1.3;">Box Elder Prospects</div>
        <div style="color:#90b8d8;font-size:13px;margin-top:6px;">
          {datetime.now().strftime('%B %d, %Y')} &bull; Activity detected on {len(changed_sources)} monitored source(s)
        </div>
      </div>
      <div style="background:#fff;border:1px solid #e2e8f0;border-top:none;
        border-radius:0 0 12px 12px;padding:26px 28px;">
        {blocks}
        <div style="font-size:11px;color:#a0aec0;font-family:Arial,sans-serif;margin-top:4px;">
          Shown above is the text added or removed on each page since the last check &mdash; not a parsed
          listing, so it may include unrelated boilerplate alongside real planning activity.
        </div>
      </div>
    </div>
    """
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(FROM_EMAIL, GMAIL_APP_PASSWORD)
        s.sendmail(FROM_EMAIL, TO_EMAIL, msg.as_string())
    print(f"  Email sent -> {TO_EMAIL}")


def main():
    send = "--no-email" not in sys.argv

    print("\nBox Elder Prospects Agent — Kevin Andreson")
    print("=" * 42)

    state = load_state()
    changed = []

    for source in SOURCES:
        print(f"\nChecking {source['name']} ({source['role']})...")
        try:
            raw_html = fetch(source["url"])
        except requests.RequestException as e:
            print(f"  FAILED to fetch: {e}")
            continue

        new_lines = extract_text_lines(raw_html)
        new_hash  = content_hash(new_lines)

        prev     = state.get(source["url"], {})
        old_hash = prev.get("hash")
        old_lines = prev.get("lines", [])

        if old_hash is None:
            print("  First check — saving baseline, no alert.")
        elif new_hash != old_hash:
            print("  CHANGED since last check.")
            changed.append({**source, "diff": diff_lines(old_lines, new_lines)})
        else:
            print("  No change.")

        state[source["url"]] = {
            "hash": new_hash,
            "lines": new_lines,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }

    save_state(state)

    if changed and send:
        print(f"\n{len(changed)} source(s) changed — sending alert email...")
        send_email(changed)
    elif changed:
        print(f"\n{len(changed)} source(s) changed — email skipped (--no-email).")
    else:
        print("\nNo changes detected — no email sent.")


if __name__ == "__main__":
    main()
