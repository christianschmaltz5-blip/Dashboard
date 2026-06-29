#!/usr/bin/env python3
"""
Paragon Inbox Parser — Kevin Andreson / Keller Williams Black Hills
Reads Christianschmaltz5@gmail.com (All Mail), finds Paragon Collaboration
Center emails, extracts individual listings, aggregates counts by price band
and property category, then writes to js/market-data.js.

Usage:
  python3 parse_paragon_inbox.py          # parse + update market-data.js
  python3 parse_paragon_inbox.py --check  # show what Paragon emails are found
  python3 parse_paragon_inbox.py --days 30  # look back 30 days (default: 14)
"""
import argparse, email, imaplib, json, os, re, sys
from datetime import datetime, timedelta
from email.header import decode_header
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(__file__))
from config import FROM_EMAIL, GMAIL_APP_PASSWORD, PRICE_BANDS, MLS_DETAIL_CATEGORIES

MARKET_DATA_JS = os.path.join(os.path.dirname(__file__), '..', '..', 'js', 'market-data.js')
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# ── Property type → MLS detail category ──────────────────────────────────────
PROP_TYPE_MAP = {
    "site built":           "Residential Resale (Single Family)",
    "single family":        "Residential Resale (Single Family)",
    "condo":                "Residential Resale (Single Family)",
    "townhouse":            "Residential Resale (Single Family)",
    "manufactured":         "Residential Resale (Single Family)",
    "multi-family":         "Commercial — Multi-Family",
    "multi family":         "Commercial — Multi-Family",
    "multifamily":          "Commercial — Multi-Family",
    "duplex":               "Commercial — Multi-Family",
    "triplex":              "Commercial — Multi-Family",
    "industrial":           "Commercial — Industrial",
    "warehouse":            "Commercial — Industrial",
    "general commercial":   "Commercial — General Commercial",
    "commercial":           "Commercial — General Commercial",
    "retail":               "Commercial — General Commercial",
    "office":               "Commercial — General Commercial",
}

# ── Status normalizer ────────────────────────────────────────────────────────
def normalize_status(raw):
    r = raw.lower().strip()
    if "under contract" in r or "pending" in r or "contingent" in r:
        return "Under Contract"
    if "sold" in r or "closed" in r:
        return "Sold"
    if "active" in r or "new" in r:
        return "Active"
    return None


class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
    def handle_data(self, d):
        self.text.append(d)
    def get_text(self):
        return "\n".join(self.text)


def strip_html(html):
    s = HTMLStripper()
    s.feed(html)
    return s.get_text()


def decode_str(s):
    if not s:
        return ""
    parts = decode_header(s)
    out = []
    for part, enc in parts:
        if isinstance(part, bytes):
            out.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(part)
    return " ".join(out)


def get_text_body(msg):
    plain, html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            try:
                payload = part.get_payload(decode=True).decode("utf-8", errors="replace")
            except Exception:
                continue
            if ct == "text/plain":
                plain += payload
            elif ct == "text/html":
                html += payload
    else:
        try:
            payload = msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            payload = ""
        ct = msg.get_content_type()
        if ct == "text/html":
            html = payload
        else:
            plain = payload
    return plain if plain.strip() else strip_html(html)


def connect():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(FROM_EMAIL, GMAIL_APP_PASSWORD)
        return mail
    except imaplib.IMAP4.error as e:
        print(f"\nIMAP login failed: {e}")
        sys.exit(1)


def fetch_paragon_emails(mail, days=14):
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    results = []

    for folder in ('"[Gmail]/All Mail"', "INBOX"):
        try:
            rv, _ = mail.select(folder, readonly=True)
            if rv != "OK":
                continue
        except Exception:
            continue

        _, ids = mail.search(None, f'(SINCE {since})')
        if not ids[0]:
            continue

        for uid in ids[0].split():
            _, data = mail.fetch(uid, "(RFC822)")
            msg     = email.message_from_bytes(data[0][1])
            sender  = decode_str(msg.get("From", ""))
            subject = decode_str(msg.get("Subject", ""))
            date    = msg.get("Date", "")

            if not _is_paragon(sender, subject):
                continue

            body = get_text_body(msg)
            results.append({"sender": sender, "subject": subject, "date": date, "body": body})

        break   # found the folder, don't double-count

    return results


def _is_paragon(sender, subject):
    sl = sender.lower();  su = subject.lower()
    # Exclude emails from Kevin's own KW address — those are not Paragon system emails
    if "kandreson@kw.com" in sl:
        return False
    return (
        any(k in sl for k in ("paragon", "noreply@kw.com", "kwls", "bhrealtors", "mtrushmoremls", "corelogic", "blackhillsrealtors"))
        or any(k in su for k in ("collaboration center", "saved search", "new listing", "mls alert", "search update"))
    )


def parse_listings(body):
    """
    Extract individual listings from a Paragon Collaboration Center email.
    Returns list of {status, price, prop_type} dicts.
    """
    listings = []
    lines = [l.strip() for l in body.splitlines() if l.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]

        # Detect a status line (e.g. "Active - ACTIVE", "New", "Under Contract")
        status = normalize_status(line)
        if status is None:
            i += 1
            continue

        # Look ahead up to 15 lines for a price and property type
        price     = None
        prop_type = None
        for j in range(i + 1, min(i + 15, len(lines))):
            l = lines[j]
            # Price: $369,900 or $1,200,000
            if price is None:
                pm = re.match(r'^\$[\d,]+$', l)
                if pm:
                    price = int(re.sub(r'[^\d]', '', l))
            # Property type keyword
            if prop_type is None:
                ll = l.lower()
                for key, cat in PROP_TYPE_MAP.items():
                    if key in ll:
                        prop_type = cat
                        break

        if price is not None:
            listings.append({
                "status":    status,
                "price":     price,
                "prop_type": prop_type or "Residential Resale (Single Family)",
            })
            i += 15   # skip past this listing block
        else:
            i += 1

    return listings


def bucket_price(price):
    for label, lo, hi in PRICE_BANDS:
        if lo <= price < hi:
            return label
    return None


def aggregate(all_listings):
    """Roll up individual listings into the detail table structure."""
    detail = {}
    for cat in MLS_DETAIL_CATEGORIES:
        detail[cat] = {}
        for band, _, _ in PRICE_BANDS:
            detail[cat][band] = {"Active": 0, "Under Contract": 0, "Sold": 0}

    for lst in all_listings:
        cat   = lst["prop_type"]
        band  = bucket_price(lst["price"])
        status = lst["status"]
        if cat in detail and band and band in detail[cat] and status in detail[cat][band]:
            detail[cat][band][status] += 1

    # Replace 0 → None so the dashboard shows "—" for empty cells
    for cat in detail:
        for band in detail[cat]:
            for s in detail[cat][band]:
                if detail[cat][band][s] == 0:
                    detail[cat][band][s] = None

    return detail


def update_market_data(detail):
    with open(MARKET_DATA_JS, 'r') as f:
        content = f.read()
    match = re.search(r'window\.MARKET_DATA\s*=\s*(\{[\s\S]*\});', content)
    if not match:
        print("ERROR: Could not parse market-data.js")
        return
    data = json.loads(match.group(1))
    data["mlsDetail"]["data"] = detail
    data["generated"] = datetime.now().strftime("%B %d, %Y")
    new_content = (
        f"// Auto-generated by mls_report.py — {datetime.now().strftime('%B %d, %Y')}\n"
        f"window.MARKET_DATA = {json.dumps(data, indent=2)};\n"
    )
    with open(MARKET_DATA_JS, 'w') as f:
        f.write(new_content)
    print(f"✓ market-data.js updated")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="Show emails found without updating")
    ap.add_argument("--days",  type=int, default=14, help="Days back to search (default: 14)")
    args = ap.parse_args()

    print(f"\nConnecting to {FROM_EMAIL} (All Mail)...")
    mail = connect()
    print("✓ Connected\n")

    print(f"Searching last {args.days} days for Paragon emails...")
    paragon_emails = fetch_paragon_emails(mail, days=args.days)
    mail.logout()
    print(f"✓ Found {len(paragon_emails)} Paragon email(s)\n")

    for e in paragon_emails:
        print(f"  · {e['date'][:16]}  |  {e['subject'][:65]}")
        print(f"    From: {e['sender'][:60]}")

    if args.check or not paragon_emails:
        if not paragon_emails:
            print("\nNo Paragon emails found.")
            print(f"Check that saved searches in Paragon are emailing {FROM_EMAIL}")
            print("or try --days 30 to look further back.")
        return

    all_listings = []
    for e in paragon_emails:
        found = parse_listings(e["body"])
        print(f"\n  Parsed {len(found)} listing(s) from: {e['subject'][:55]}")
        for lst in found:
            band = bucket_price(lst["price"])
            print(f"    {lst['status']:15}  ${lst['price']:>10,}  ({band})  →  {lst['prop_type']}")
        all_listings.extend(found)

    if not all_listings:
        print("\nEmails found but no individual listings could be parsed.")
        print("Run --check and forward a sample email for format review.")
        return

    detail = aggregate(all_listings)
    update_market_data(detail)

    total = sum(
        v for cat in detail.values()
        for band in cat.values()
        for v in band.values()
        if v
    )
    print(f"\n✓ Done — {len(all_listings)} listings aggregated into MLS detail table ({total} non-empty cells)")


if __name__ == "__main__":
    main()
