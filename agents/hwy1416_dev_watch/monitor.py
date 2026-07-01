"""
Highway 1416 Development Watch — Kevin Andreson
Weekly scan of Box Elder + Pennington County planning/zoning listings for new
activity within 10 miles of Highway 1416 (Box Elder / Ellsworth AFB gate).
Diffs each source against last run, has Claude pull out a structured item per
new/changed entry (address + summary), geocodes each address, and keeps only
items within RADIUS_MILES. Items with no extractable address are kept in a
separate "location unclear" section rather than silently dropped, since we'd
rather Kevin double check one than miss a real hit.

Run:  python3 monitor.py            <- checks sources, emails digest if anything in range
      python3 monitor.py --no-email <- checks sources, prints result, no email
"""

import hashlib
import html as html_lib
import json
import math
import os
import re
import smtplib
import sys
import time
import difflib
from io import BytesIO
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from urllib.parse import urljoin

import cloudscraper
import requests
import pdfplumber
from anthropic import Anthropic

from config import (
    FROM_EMAIL, TO_EMAIL, GMAIL_APP_PASSWORD,
    ANTHROPIC_API_KEY, CLAUDE_MODEL, SOURCES,
    HWY_1416_ANCHOR, RADIUS_MILES, STATE_FILE,
)

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), STATE_FILE)

SCRIPT_STYLE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
BLOCK_BREAK  = re.compile(r"</?(div|p|li|tr|td|th|h[1-6]|br|ul|ol|table)[^>]*>", re.I)
TAG          = re.compile(r"<[^>]+>")
LINK         = re.compile(r'<a\s+[^>]*href=["\']([^"\']+)["\']', re.I)

LINK_KEYWORDS = ("agenda", "packet", "minutes", ".pdf")

scraper = cloudscraper.create_scraper()


def fetch(url):
    r = scraper.get(url, timeout=25)
    r.raise_for_status()
    return r


def extract_text_lines(raw_html):
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


# ── Geocoding + distance ─────────────────────────────────────────────────────

def geocode(address):
    """US Census Geocoder — free, no API key. Returns (lat, lon) or None."""
    try:
        r = requests.get(
            "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
            params={"address": address, "benchmark": "Public_AR_Current", "format": "json"},
            timeout=15,
        )
        r.raise_for_status()
        matches = r.json().get("result", {}).get("addressMatches", [])
        if not matches:
            return None
        coords = matches[0]["coordinates"]
        return (coords["y"], coords["x"])  # (lat, lon)
    except Exception:
        return None


def miles_between(p1, p2):
    """Haversine distance in miles."""
    lat1, lon1 = map(math.radians, p1)
    lat2, lon2 = map(math.radians, p2)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 3958.8 * math.asin(math.sqrt(a))


# ── Claude extraction ────────────────────────────────────────────────────────

EXTRACT_PROMPT = """You monitor Box Elder / Pennington County, SD planning portals for real estate development activity near Highway 1416 (Box Elder, next to Ellsworth AFB).

From the new/changed text below, extract each distinct development item (rezoning, conditional use permit, variance, subdivision plat, annexation, building permit). Skip routine administrative items (minutes approval, scheduling housekeeping) with no parcel or development content.

For each item return:
- "address": the parcel address, or as specific a location description as given (cross streets, subdivision name, section/township/range). Use null if truly no location is stated anywhere in the text.
- "summary": 1-2 sentence plain-English description of what's being requested, including the outcome/discussion if the text includes meeting minutes or a vote.
- "hearing_date": date if stated, else null.

Respond with ONLY a JSON array, e.g.:
[{"address": "123 Main St, Box Elder, SD", "summary": "...", "hearing_date": "2026-07-10"}]
If there are no development items, respond with exactly: []

Source: {source_name}
Text:
{text}"""


def extract_items(client, source_name, new_text):
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": EXTRACT_PROMPT.format(source_name=source_name, text=new_text[:20000]),
        }],
    )
    raw = msg.content[0].text.strip()
    match = re.search(r'\[[\s\S]*\]', raw)
    if not match:
        return []
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return []


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(in_range, unclear, unreachable):
    subject = f"New Development (5-10 mi) of Highway 1416 · {datetime.now().strftime('%b %d')}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"]   = TO_EMAIL

    row = "font-size:13px;color:#1a202c;line-height:1.7;font-family:Arial,sans-serif;"

    def item_block(source, item, distance=None):
        dist_line = f"<div style='font-size:11px;color:#4a5568;margin-top:6px;'>~{distance:.1f} mi from Hwy 1416</div>" if distance is not None else ""
        addr = item.get("address") or "Location not stated in source text"
        date = f" &bull; {item['hearing_date']}" if item.get("hearing_date") else ""
        return f"""
        <div style="margin-bottom:16px;border:1px solid #e2e8f0;border-radius:10px;padding:16px 20px;">
          <div style="font-size:11px;font-weight:700;color:#7fb3e0;text-transform:uppercase;letter-spacing:0.05em;font-family:Arial,sans-serif;">{source}{date}</div>
          <div style="font-size:13px;font-weight:700;color:#0f2942;font-family:Arial,sans-serif;margin:6px 0 4px;">{addr}</div>
          <div style="{row}">{item.get('summary', '')}</div>
          {dist_line}
        </div>"""

    blocks = "".join(item_block(s, i, d) for s, i, d in in_range)

    unclear_html = ""
    if unclear:
        items = "".join(f"<li style='margin-bottom:8px;'><b>[{s}]</b> {i.get('address') or 'no location given'} — {i.get('summary','')}</li>" for s, i in unclear)
        unclear_html = f"""
        <div style="margin-top:8px;padding:14px 18px;background:#fffbeb;border:1px solid #fde68a;border-radius:8px;">
          <div style="font-size:11px;font-weight:700;color:#92400e;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;font-family:Arial,sans-serif;">Could not confirm distance — review manually</div>
          <ul style="font-size:12px;color:#92400e;font-family:Arial,sans-serif;margin:0;padding-left:18px;">{items}</ul>
        </div>"""

    unreachable_html = ""
    if unreachable:
        items = "".join(f"<li style='margin-bottom:4px;'>{n}</li>" for n in unreachable)
        unreachable_html = f"""
        <div style="margin-top:8px;padding:14px 18px;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;">
          <div style="font-size:11px;font-weight:700;color:#991b1b;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;font-family:Arial,sans-serif;">Could not check this run</div>
          <ul style="font-size:12px;color:#991b1b;font-family:Arial,sans-serif;margin:0;padding-left:18px;">{items}</ul>
        </div>"""

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;">
      <div style="background:#0f2942;border-radius:12px 12px 0 0;padding:28px 32px 24px;">
        <div style="color:#7fb3e0;font-size:11px;font-weight:700;letter-spacing:0.08em;
          text-transform:uppercase;margin-bottom:6px;">Highway 1416 Development Watch</div>
        <div style="color:#fff;font-size:22px;font-weight:800;line-height:1.3;">New Development Near Highway 1416</div>
        <div style="color:#90b8d8;font-size:13px;margin-top:6px;">
          {datetime.now().strftime('%B %d, %Y')} &bull; within {RADIUS_MILES} miles &bull; Box Elder / Pennington County
        </div>
      </div>
      <div style="background:#fff;border:1px solid #e2e8f0;border-top:none;
        border-radius:0 0 12px 12px;padding:26px 28px;">
        {blocks if blocks else "<div style='font-size:13px;color:#718096;'>No confirmed in-range items this week.</div>"}
        {unclear_html}
        {unreachable_html}
        <div style="font-size:11px;color:#a0aec0;font-family:Arial,sans-serif;margin-top:14px;">
          Locations are auto-geocoded from posted agenda text and may be approximate — verify before acting.
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
        print("ANTHROPIC_API_KEY is not set in config.py — cannot extract items. Aborting.")
        sys.exit(1)

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    print("\nHighway 1416 Development Watch — Kevin Andreson")
    print("=" * 48)

    state = load_state()
    in_range = []   # (source_name, item, distance_miles)
    unclear = []    # (source_name, item)
    unreachable = []

    for source in SOURCES:
        name, url = source["name"], source["url"]
        print(f"\nChecking {name}...")
        try:
            r = fetch(url)
        except Exception as e:
            print(f"  FAILED to fetch: {e}")
            unreachable.append(name)
            continue

        new_lines = extract_text_lines(r.text)
        new_links = extract_links(r.text, url)
        new_hash  = content_hash(new_lines)

        prev = state.get(url, {})
        old_hash = prev.get("hash")
        old_lines = prev.get("lines", [])
        old_links = set(prev.get("links", []))

        if old_hash is None:
            print("  First check — saving baseline, no alert.")
            state[url] = {
                "hash": new_hash, "lines": new_lines, "links": list(new_links),
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
                items = extract_items(client, name, combined)
            except Exception as e:
                print(f"  Claude extraction failed: {e}")
                items = []

            for item in items:
                addr = item.get("address")
                if not addr:
                    unclear.append((name, item))
                    continue
                geo_query = addr if "SD" in addr.upper() else f"{addr}, Pennington County, SD"
                point = geocode(geo_query)
                time.sleep(0.5)  # be polite to the free Census geocoder
                if point is None:
                    unclear.append((name, item))
                    continue
                dist = miles_between(HWY_1416_ANCHOR, point)
                if dist <= RADIUS_MILES:
                    print(f"  In range ({dist:.1f} mi): {addr}")
                    in_range.append((name, item, dist))
                else:
                    print(f"  Out of range ({dist:.1f} mi), skipped: {addr}")
        else:
            print("  No change.")

        state[url] = {
            "hash": new_hash, "lines": new_lines, "links": list(new_links),
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }

    save_state(state)

    if (in_range or unclear) and send:
        print(f"\n{len(in_range)} in-range, {len(unclear)} unclear — sending digest email...")
        send_email(in_range, unclear, unreachable)
    elif in_range or unclear:
        print(f"\n{len(in_range)} in-range, {len(unclear)} unclear — email skipped (--no-email).")
    else:
        print("\nNothing new near Highway 1416 this week — no email sent.")


if __name__ == "__main__":
    main()
