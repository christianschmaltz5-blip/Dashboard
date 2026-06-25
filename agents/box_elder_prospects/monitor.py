"""
Box Elder Prospects Agent — Kevin Andreson
Watches Box Elder, SD Planning & Zoning (primary) and Pennington County
Planning hearing schedules (secondary). Diffs each source's page against the
last run, fetches the text of any newly-appeared linked PDF/agenda-item page,
and has Claude write a plain-English digest of new parcels, new development
activity, and the discussion around it — emailing only when something is
actually development-significant. Intended to run Friday via run.sh.

Run:  python3 monitor.py            <- checks sources, emails digest if anything notable
      python3 monitor.py --no-email <- checks sources, prints result, no email
"""

import hashlib
import html as html_lib
import json
import os
import re
import smtplib
import sys
import difflib
import requests
from io import BytesIO
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from urllib.parse import urljoin

import pdfplumber
from anthropic import Anthropic

from config import (
    FROM_EMAIL, TO_EMAIL, GMAIL_APP_PASSWORD,
    ANTHROPIC_API_KEY, CLAUDE_MODEL, SOURCES, STATE_FILE,
)

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), STATE_FILE)

SCRIPT_STYLE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
BLOCK_BREAK  = re.compile(r"</?(div|p|li|tr|td|th|h[1-6]|br|ul|ol|table)[^>]*>", re.I)
TAG          = re.compile(r"<[^>]+>")
LINK         = re.compile(r'<a\s+[^>]*href=["\']([^"\']+)["\']', re.I)

# Links worth tracking as "items" — agenda/packet/minutes pages or PDFs.
LINK_KEYWORDS = ("agenda", "packet", "minutes", ".pdf")


def fetch(url):
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (ARC Box Elder Prospects monitor)"}, timeout=20)
    r.raise_for_status()
    return r


def extract_text_lines(raw_html):
    # Strip script/style blocks entirely (noise — analytics IDs, inline JS),
    # then turn block-level tags into line breaks so the result reads like
    # actual page text instead of one giant run-on line.
    text = SCRIPT_STYLE.sub(" ", raw_html)
    text = BLOCK_BREAK.sub("\n", text)
    text = TAG.sub("", text)
    text = html_lib.unescape(text)
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def extract_links(raw_html, base_url):
    found = set()
    for href in LINK.findall(raw_html):
        absolute = urljoin(base_url, href)
        if any(k in absolute.lower() for k in LINK_KEYWORDS):
            found.add(absolute)
    return found


def extract_pdf_text(content_bytes):
    try:
        with pdfplumber.open(BytesIO(content_bytes)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as e:
        return f"[Could not read PDF: {e}]"


def fetch_linked_text(url):
    """Best-effort fetch of a newly-appeared link — PDF or HTML."""
    try:
        r = fetch(url)
    except Exception as e:
        return f"[Could not fetch {url}: {e}]"
    ctype = r.headers.get("Content-Type", "")
    if "pdf" in ctype.lower() or url.lower().endswith(".pdf"):
        return extract_pdf_text(r.content)
    return "\n".join(extract_text_lines(r.text))


def content_hash(lines):
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


SYSTEM_PROMPT = """You monitor planning and zoning activity for Box Elder, South Dakota (57719) and Pennington County hearings affecting it, on behalf of Kevin Andreson, a Keller Williams agent prospecting light industrial and multi-family land near Ellsworth Air Force Base and the I-90 corridor.

Kevin cares about three things, in this order:
1. New parcels — any address, subdivision, or plat appearing for the first time.
2. New land development activity on those parcels — rezonings, conditional use permits, building permits, plats, variances, annexations.
3. The discussion around it — if the supplied text includes meeting minutes, agenda packets, staff reports, or commissioner/public comments, summarize what was actually said: arguments for/against, conditions attached, vote outcome, staff recommendation. Don't just report that a hearing happened — report what happened at it, when that detail is available.

For each item found:
1. Identify the parcel (address, APN, acreage if available)
2. Summarize what is being requested in plain English (2-3 sentences max)
3. Summarize the discussion/outcome if the source text contains it
4. Flag why it matters to Kevin (development opportunity, market signal, competitor activity) — industrial and multi-family first
5. Note the hearing date or decision status

Skip routine administrative items (minutes approval, scheduling housekeeping, etc.) with no parcel or development content. Only surface items with real development significance.
Output as a clean digest, one paragraph per item, sorted by urgency — large parcels and industrial zoning near Ellsworth AFB first.
If nothing in the supplied text has development significance, respond with exactly: NONE"""


def summarize(client, source_name, new_text):
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"New/changed content just found on the {source_name} planning page:\n\n{new_text[:20000]}",
        }],
    )
    return msg.content[0].text.strip()


def _digest_subject(digests):
    """Pull the top finding from the first digest as the email headline."""
    if not digests:
        return f"Box Elder — New Activity — {datetime.now().strftime('%b %d')}"
    # First sentence of the first (highest-priority) digest
    import re
    text = digests[0][1]
    m = re.search(r'([A-Z][^.!?\n]{20,}[.!?])', text)
    headline = m.group(1).strip() if m else text[:80].strip()
    if len(headline) > 90:
        headline = headline[:87] + "..."
    return f"{headline} · {datetime.now().strftime('%b %d')}"


def send_email(digests, unreachable):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = _digest_subject(digests)
    msg["From"] = FROM_EMAIL
    msg["To"]   = TO_EMAIL

    row = "font-size:13px;color:#1a202c;line-height:1.7;font-family:Arial,sans-serif;white-space:pre-wrap;"

    blocks = ""
    for name, text in digests:
        blocks += f"""
        <div style="margin-bottom:20px;border:1px solid #e2e8f0;border-radius:10px;padding:20px 22px;">
          <div style="font-size:14px;font-weight:700;color:#0f2942;font-family:Arial,sans-serif;margin-bottom:10px;">{name}</div>
          <div style="{row}">{text}</div>
        </div>"""

    if unreachable:
        items = "".join(f"<li style='margin-bottom:4px;'>{n}</li>" for n in unreachable)
        blocks += f"""
        <div style="margin-top:8px;padding:14px 18px;background:#fffbeb;border:1px solid #fde68a;border-radius:8px;">
          <div style="font-size:11px;font-weight:700;color:#92400e;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;font-family:Arial,sans-serif;">Could not check this run</div>
          <ul style="font-size:12px;color:#92400e;font-family:Arial,sans-serif;margin:0;padding-left:18px;">{items}</ul>
        </div>"""

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;">
      <div style="background:#0f2942;border-radius:12px 12px 0 0;padding:28px 32px 24px;">
        <div style="color:#7fb3e0;font-size:11px;font-weight:700;letter-spacing:0.08em;
          text-transform:uppercase;margin-bottom:6px;">Planning &amp; Zoning Alert</div>
        <div style="color:#fff;font-size:22px;font-weight:800;line-height:1.3;">Box Elder Prospects</div>
        <div style="color:#90b8d8;font-size:13px;margin-top:6px;">
          {datetime.now().strftime('%B %d, %Y')} &bull; {len(digests)} source(s) with development-significant activity
        </div>
      </div>
      <div style="background:#fff;border:1px solid #e2e8f0;border-top:none;
        border-radius:0 0 12px 12px;padding:26px 28px;">
        {blocks}
        <div style="font-size:11px;color:#a0aec0;font-family:Arial,sans-serif;margin-top:4px;">
          Summaries are AI-generated from each source's posted page/agenda text &mdash; verify details against
          the original filing before acting.
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

    if not ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY is not set in config.py — cannot summarize. Aborting.")
        sys.exit(1)

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    print("\nBox Elder Prospects Agent — Kevin Andreson")
    print("=" * 42)

    state = load_state()
    digests = []
    unreachable = []

    for source in SOURCES:
        name, url = source["name"], source["url"]
        print(f"\nChecking {name} ({source['role']})...")
        try:
            r = fetch(url)
        except requests.RequestException as e:
            print(f"  FAILED to fetch: {e}")
            unreachable.append(name)
            continue

        new_lines = extract_text_lines(r.text)
        new_links = extract_links(r.text, url)
        new_hash  = content_hash(new_lines)

        prev      = state.get(url, {})
        old_hash  = prev.get("hash")
        old_lines = prev.get("lines", [])
        old_links = set(prev.get("links", []))

        if old_hash is None:
            print("  First check — saving baseline, no alert.")
            state[url] = {
                "hash": new_hash,
                "lines": new_lines,
                "links": list(new_links),
                "checked_at": datetime.now().isoformat(timespec="seconds"),
            }
            continue

        new_content_chunks = []
        if new_hash != old_hash:
            diff = [d[2:] for d in difflib.ndiff(old_lines, new_lines) if d.startswith("+ ")]
            if diff:
                new_content_chunks.append("\n".join(diff))

        for link in new_links - old_links:
            print(f"  New linked item: {link}")
            new_content_chunks.append(f"[{link}]\n{fetch_linked_text(link)}")

        if new_content_chunks:
            combined = "\n\n---\n\n".join(new_content_chunks)
            try:
                summary = summarize(client, name, combined)
            except Exception as e:
                print(f"  Claude summarization failed: {e}")
                summary = None
            if summary and summary.strip() != "NONE":
                print("  Development-significant activity found.")
                digests.append((name, summary))
            else:
                print("  Changed, but nothing development-significant.")
        else:
            print("  No change.")

        state[url] = {
            "hash": new_hash,
            "lines": new_lines,
            "links": list(new_links),
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }

    save_state(state)

    if digests and send:
        print(f"\n{len(digests)} source(s) with significant activity — sending digest email...")
        send_email(digests, unreachable)
    elif digests:
        print(f"\n{len(digests)} source(s) with significant activity — email skipped (--no-email).")
    else:
        print("\nNo development-significant activity detected — no email sent.")


if __name__ == "__main__":
    main()
