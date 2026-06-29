#!/usr/bin/env python3
"""
LoopNet Alert Parser — Kevin Andreson / Keller Williams Black Hills
Reads Gmail inbox for LoopNet listing alert emails, parses each property,
and writes js/loopnet-listings.js for the dashboard.

Primary inbox: arecblackhills@gmail.com (needs App Password in config.py)
Fallback inbox: Christianschmaltz5@gmail.com (working App Password already set)

Usage:
  python3 parse_loopnet_inbox.py             # parse + update loopnet-listings.js
  python3 parse_loopnet_inbox.py --check     # show emails found, don't write output
  python3 parse_loopnet_inbox.py --days 30   # look back 30 days (default 21)
  python3 parse_loopnet_inbox.py --email     # also email a summary to arecblackhills
"""
import argparse, email, imaplib, json, os, re, sys, smtplib
from datetime import datetime, timedelta
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    IMAP_EMAIL, IMAP_APP_PASSWORD,
    FROM_EMAIL, GMAIL_APP_PASSWORD,
    TO_EMAIL,
    LOOPNET_SENDER_KEYWORDS, LOOPNET_SUBJECT_KEYWORDS,
    PROP_TYPE_MAP, SD_MARKETS,
)

LOOPNET_JS = os.path.join(os.path.dirname(__file__), '..', '..', 'js', 'loopnet-listings.js')
IMAP_HOST  = "imap.gmail.com"
IMAP_PORT  = 993
SMTP_HOST  = "smtp.gmail.com"
SMTP_PORT  = 587


# ── HTML → Text ───────────────────────────────────────────────────────────────
class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._lines = []
        self._in_a  = False
        self._href  = ""
        self._links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._in_a = True
            for k, v in attrs:
                if k == "href" and v and v.startswith("http"):
                    self._href = v
        if tag in ("br", "p", "tr", "div", "li", "h1", "h2", "h3", "h4"):
            self._lines.append("\n")

    def handle_endtag(self, tag):
        if tag == "a":
            if self._href:
                self._links.append(self._href)
            self._in_a = False
            self._href = ""
        if tag in ("p", "tr", "div", "li", "h1", "h2", "h3", "h4"):
            self._lines.append("\n")

    def handle_data(self, d):
        stripped = d.strip()
        if stripped:
            self._lines.append(stripped)

    def get_text(self):
        return " ".join(self._lines)

    def get_links(self):
        return self._links


def strip_html(html):
    s = HTMLStripper()
    s.feed(html)
    return s.get_text(), s.get_links()


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


def get_body(msg):
    plain, html = "", ""
    links = []
    if msg.is_multipart():
        for part in msg.walk():
            ct  = part.get_content_type()
            cd  = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            try:
                payload = part.get_payload(decode=True).decode("utf-8", errors="replace")
            except Exception:
                continue
            if ct == "text/plain":
                plain += payload
            elif ct == "text/html":
                t, l = strip_html(payload)
                html  += t
                links += l
    else:
        try:
            payload = msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            payload = ""
        ct = msg.get_content_type()
        if ct == "text/html":
            html, links = strip_html(payload)
        else:
            plain = payload

    return (plain if plain.strip() else html), links


# ── IMAP ──────────────────────────────────────────────────────────────────────
def connect():
    # Try arecblackhills first (if App Password is configured)
    if IMAP_APP_PASSWORD.strip():
        try:
            m = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            m.login(IMAP_EMAIL, IMAP_APP_PASSWORD)
            print(f"✓ Connected to {IMAP_EMAIL}")
            return m, IMAP_EMAIL
        except imaplib.IMAP4.error as e:
            print(f"  arecblackhills login failed ({e}) — falling back to {FROM_EMAIL}")

    # Fallback: Christianschmaltz5 (working App Password)
    try:
        m = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        m.login(FROM_EMAIL, GMAIL_APP_PASSWORD)
        print(f"✓ Connected to {FROM_EMAIL}")
        print(f"  NOTE: Reading {FROM_EMAIL}. To read {IMAP_EMAIL} directly,")
        print(f"  add an App Password in config.py, OR set up Gmail forwarding:")
        print(f"  {IMAP_EMAIL} → Settings → Forwarding → {FROM_EMAIL}")
        return m, FROM_EMAIL
    except imaplib.IMAP4.error as e:
        print(f"\nIMAP login failed: {e}")
        sys.exit(1)


def fetch_loopnet_emails(mail, days=21):
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

            if not _is_loopnet(sender, subject):
                continue

            body, links = get_body(msg)
            results.append({
                "sender":  sender,
                "subject": subject,
                "date":    date,
                "body":    body,
                "links":   links,
            })

        break  # stop after first folder that works

    return results


def _is_loopnet(sender, subject):
    sl = sender.lower()
    su = subject.lower()
    return (
        any(k in sl for k in LOOPNET_SENDER_KEYWORDS)
        or any(k in su for k in LOOPNET_SUBJECT_KEYWORDS)
    )


# ── Listing parser ────────────────────────────────────────────────────────────
def normalize_type(text):
    tl = text.lower()
    for key, label in PROP_TYPE_MAP.items():
        if key in tl:
            return label
    return "Commercial"


def parse_price(text):
    """Return int dollars or None. Handles $1,250,000 and $1.25M."""
    text = text.strip()
    m = re.search(r'\$([\d,]+(?:\.\d+)?)\s*(M|K)?', text, re.IGNORECASE)
    if not m:
        return None
    num_str = m.group(1).replace(',', '')
    mult    = m.group(2) or ''
    num = float(num_str)
    if mult.upper() == 'M':
        num *= 1_000_000
    elif mult.upper() == 'K':
        num *= 1_000
    return int(num)


def parse_sf(text):
    m = re.search(r'([\d,]+)\s*(?:SF|sq\.?\s*ft\.?|square\s*feet)', text, re.IGNORECASE)
    if m:
        return int(m.group(1).replace(',', ''))
    return None


def parse_acres(text):
    m = re.search(r'([\d.]+)\s*(?:acres?|AC\b)', text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


def parse_cap_rate(text):
    m = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
    if m:
        val = float(m.group(1))
        if 2.0 <= val <= 20.0:   # sanity check — cap rates are 2–20%
            return val
    return None


def is_sd_market(text):
    tl = text.lower()
    return any(city.lower() in tl for city in SD_MARKETS)


def parse_loopnet_email(email_data):
    """
    Parse a LoopNet alert email into a list of listing dicts.

    LoopNet alert emails have one block per property. We split on
    common property-separator patterns and extract fields from each block.
    """
    body  = email_data["body"]
    links = email_data["links"]
    date_raw = email_data["date"]

    # Parse alert date
    try:
        from email.utils import parsedate_to_datetime
        alert_dt   = parsedate_to_datetime(date_raw)
        alert_date = alert_dt.strftime("%Y-%m-%d")
    except Exception:
        alert_date = datetime.now().strftime("%Y-%m-%d")

    # LoopNet listing URLs (loopnet.com/listing/... pattern)
    listing_urls = [l for l in links if "loopnet.com/listing" in l.lower() or "loopnet.com/commercial" in l.lower()]

    lines = [l.strip() for l in re.split(r'[\n\r]+', body) if l.strip()]
    listings = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # A property type keyword in a short line usually starts a listing block
        is_type_line = (
            len(line) < 60
            and any(k in line.lower() for k in PROP_TYPE_MAP.keys())
            and not any(skip in line.lower() for skip in ("search", "filter", "view all", "click", "manage"))
        )

        # OR: a line that looks like an address (has "SD" or a city name)
        is_address_line = (
            bool(re.search(r',\s*(SD|South Dakota)\b', line, re.IGNORECASE))
            or is_sd_market(line)
        )

        if not (is_type_line or is_address_line):
            i += 1
            continue

        # Scan the surrounding window (up to 20 lines) for property fields
        window_start = max(0, i - 3)
        window_end   = min(len(lines), i + 20)
        window       = lines[window_start:window_end]
        window_text  = " | ".join(window)

        # Address: prefer a line with "SD" or a known city
        address = None
        for wl in window:
            if re.search(r',\s*(SD|South Dakota)\b', wl, re.IGNORECASE) or is_sd_market(wl):
                address = wl
                break
        if not address:
            for wl in window:
                # any line that looks like "123 Main St, City"
                if re.match(r'\d+\s+\w', wl) and ',' in wl:
                    address = wl
                    break

        # Price
        price         = None
        price_display = "Call for Price"
        for wl in window:
            if "call for price" in wl.lower() or "call for pricing" in wl.lower():
                price_display = "Call for Price"
                break
            p = parse_price(wl)
            if p and p > 50_000:
                price         = p
                price_display = "$" + f"{p:,}"
                break
        # Also scan full window text for price if not found line-by-line
        if price is None:
            p = parse_price(window_text)
            if p and p > 50_000:
                price         = p
                price_display = "$" + f"{p:,}"

        # Property type
        prop_type = None
        for wl in window:
            pt = normalize_type(wl)
            if pt != "Commercial":
                prop_type = pt
                break
        if not prop_type:
            prop_type = normalize_type(window_text)

        # SF / Acres
        sf    = parse_sf(window_text)
        acres = parse_acres(window_text)

        # Cap rate
        cap_rate = None
        for wl in window:
            if "cap" in wl.lower():
                cap_rate = parse_cap_rate(wl)
                if cap_rate:
                    break
        if not cap_rate:
            # Try to find near "cap rate" in full text
            cr_m = re.search(r'cap\s*rate[:\s]+([\d.]+)\s*%', window_text, re.IGNORECASE)
            if cr_m:
                val = float(cr_m.group(1))
                if 2.0 <= val <= 20.0:
                    cap_rate = val

        # Broker / company (typically appears after broker keywords)
        broker = None
        for wl in window:
            if re.search(r'\b(broker|agent|listed by|contact|advisor)\b', wl, re.IGNORECASE):
                # next line is often the broker name
                idx = window.index(wl)
                if idx + 1 < len(window):
                    broker_line = window[idx + 1].strip()
                    if 3 < len(broker_line) < 60 and not any(c.isdigit() for c in broker_line[:6]):
                        broker = broker_line

        # Skip if we can't determine at minimum an address or price
        if address is None and price is None:
            i += 1
            continue

        # Matching LoopNet URL (try to align by index)
        url = None
        if listing_urls:
            url_idx = len(listings)
            if url_idx < len(listing_urls):
                url = listing_urls[url_idx]

        # Deduplicate (same address + price already in list)
        key = (address, price)
        if any((l.get("address"), l.get("price")) == key for l in listings):
            i += 5
            continue

        listings.append({
            "address":       address or "Address not parsed",
            "type":          prop_type or "Commercial",
            "price":         price,
            "price_display": price_display,
            "sf":            sf,
            "acres":         acres,
            "cap_rate":      cap_rate,
            "broker":        broker,
            "url":           url,
            "alert_date":    alert_date,
            "subject":       email_data["subject"],
        })
        i += 15   # skip past this listing block

    return listings


# ── JS output ─────────────────────────────────────────────────────────────────
def build_summary(listings):
    by_type = {}
    prices  = [l["price"] for l in listings if l["price"]]
    for l in listings:
        t = l["type"]
        by_type[t] = by_type.get(t, 0) + 1

    return {
        "total":       len(listings),
        "by_type":     by_type,
        "avg_price":   int(sum(prices) / len(prices)) if prices else None,
        "price_range": {
            "min": min(prices) if prices else None,
            "max": max(prices) if prices else None,
        },
    }


def write_loopnet_js(listings):
    summary = build_summary(listings)
    data = {
        "generated": datetime.now().strftime("%B %d, %Y at %I:%M %p"),
        "listings":  listings,
        "summary":   summary,
    }
    content = (
        f"// Auto-generated by parse_loopnet_inbox.py — {datetime.now().strftime('%B %d, %Y')}\n"
        f"window.LOOPNET_DATA = {json.dumps(data, indent=2)};\n"
    )
    os.makedirs(os.path.dirname(LOOPNET_JS), exist_ok=True)
    with open(LOOPNET_JS, 'w') as f:
        f.write(content)
    print(f"\n✓ loopnet-listings.js updated — {len(listings)} listings, {len(summary['by_type'])} types")


# ── Email summary ─────────────────────────────────────────────────────────────
def send_email_summary(listings):
    if not listings:
        return

    summary    = build_summary(listings)
    total      = summary["total"]
    by_type    = summary["by_type"]
    avg_price  = summary["avg_price"]
    price_range = summary["price_range"]

    type_rows = "".join(
        f"<tr><td style='padding:8px 16px;border-bottom:1px solid #111;'>{t}</td>"
        f"<td style='padding:8px 16px;border-bottom:1px solid #111;text-align:right;font-weight:700;'>{n}</td></tr>"
        for t, n in sorted(by_type.items(), key=lambda x: -x[1])
    )

    listing_cards = ""
    for l in listings[:20]:   # cap preview at 20
        price_str = l["price_display"]
        sf_str    = f"{l['sf']:,} SF" if l["sf"] else ""
        ac_str    = f"{l['acres']} AC" if l["acres"] else ""
        size_str  = sf_str or ac_str or ""
        cap_str   = f"Cap: {l['cap_rate']:.1f}%" if l["cap_rate"] else ""
        url_tag   = f'<a href="{l["url"]}" style="color:#60A5FA;font-size:11px;">View on LoopNet →</a>' if l["url"] else ""

        listing_cards += f"""
        <tr>
          <td style="padding:10px 16px;border-bottom:1px solid #111;vertical-align:top;">
            <div style="font-size:12px;font-weight:700;color:#fff;">{l['address']}</div>
            <div style="font-size:11px;color:#6B7280;margin-top:2px;">{l['type']}{' · ' + size_str if size_str else ''}{' · ' + cap_str if cap_str else ''}</div>
            {url_tag}
          </td>
          <td style="padding:10px 16px;border-bottom:1px solid #111;text-align:right;font-size:12px;font-weight:700;color:{'#34D399' if l['price'] else '#6B7280'};">{price_str}</td>
        </tr>"""

    avg_str = f"${avg_price:,}" if avg_price else "N/A"
    pmin    = f"${price_range['min']:,}" if price_range['min'] else "N/A"
    pmax    = f"${price_range['max']:,}" if price_range['max'] else "N/A"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"/></head>
<body style="background:#0A0A0A;color:#fff;font-family:Arial,sans-serif;margin:0;padding:0;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;padding:24px 16px;">
  <tr><td>
    <div style="font-size:11px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#6B7280;margin-bottom:6px;">KELLER WILLIAMS REALTY BLACK HILLS</div>
    <h1 style="font-size:22px;margin:0 0 4px;">LoopNet Alert Summary</h1>
    <div style="font-size:12px;color:#6B7280;margin-bottom:24px;">Generated {datetime.now().strftime('%B %d, %Y')} — Kevin Andreson</div>

    <table width="100%" cellpadding="0" cellspacing="0" style="background:#111;border-radius:10px;margin-bottom:20px;">
      <tr>
        <td style="padding:16px;text-align:center;"><div style="font-size:28px;font-weight:700;">{total}</div><div style="font-size:10px;color:#6B7280;text-transform:uppercase;letter-spacing:.08em;">New Listings</div></td>
        <td style="padding:16px;text-align:center;border-left:1px solid #1F1F1F;"><div style="font-size:18px;font-weight:700;">{avg_str}</div><div style="font-size:10px;color:#6B7280;text-transform:uppercase;letter-spacing:.08em;">Avg Price</div></td>
        <td style="padding:16px;text-align:center;border-left:1px solid #1F1F1F;"><div style="font-size:14px;font-weight:700;">{pmin}<br/>–&nbsp;{pmax}</div><div style="font-size:10px;color:#6B7280;text-transform:uppercase;letter-spacing:.08em;">Price Range</div></td>
      </tr>
    </table>

    <div style="font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#4B5563;margin-bottom:8px;">By Property Type</div>
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#111;border-radius:8px;margin-bottom:20px;font-size:12px;color:#9CA3AF;">
      {type_rows}
    </table>

    <div style="font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#4B5563;margin-bottom:8px;">Listings</div>
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#111;border-radius:8px;font-size:12px;color:#9CA3AF;">
      {listing_cards}
    </table>

    {'<div style="font-size:11px;color:#4B5563;margin-top:8px;text-align:center;">Showing first 20 of ' + str(total) + ' listings</div>' if total > 20 else ''}

    <div style="margin-top:24px;font-size:11px;color:#374151;text-align:center;">
      Kevin Andreson | Keller Williams Realty Black Hills<br/>
      arecblackhills@gmail.com
    </div>
  </td></tr>
</table>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"LoopNet Alert — {total} New Listings ({datetime.now().strftime('%b %d')})"
    msg["From"]    = FROM_EMAIL
    msg["To"]      = TO_EMAIL
    msg["Reply-To"] = TO_EMAIL
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(FROM_EMAIL, GMAIL_APP_PASSWORD)
            s.sendmail(FROM_EMAIL, TO_EMAIL, msg.as_string())
        print(f"✓ Summary email sent to {TO_EMAIL}")
    except Exception as e:
        print(f"  Email failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Parse LoopNet alert emails from Gmail")
    ap.add_argument("--check", action="store_true", help="Show emails found, don't update JS")
    ap.add_argument("--days",  type=int, default=21, help="Days back to search (default: 21)")
    ap.add_argument("--email", action="store_true", help="Also send summary email to arecblackhills")
    args = ap.parse_args()

    print(f"\nConnecting to Gmail via IMAP...")
    mail, inbox_email = connect()
    print()

    print(f"Searching last {args.days} days for LoopNet alert emails...")
    loopnet_emails = fetch_loopnet_emails(mail, days=args.days)
    mail.logout()
    print(f"✓ Found {len(loopnet_emails)} LoopNet email(s)\n")

    if not loopnet_emails:
        print("No LoopNet emails found.")
        print()
        print("Troubleshooting:")
        print(f"  1. Make sure LoopNet saved searches email to {inbox_email}")
        print(f"  2. Try --days 60 to look further back")
        print(f"  3. Run --check to confirm email detection patterns")
        return

    for e in loopnet_emails:
        print(f"  · {e['date'][:16]}  |  {e['subject'][:70]}")

    if args.check:
        return

    print()
    all_listings = []
    for e in loopnet_emails:
        found = parse_loopnet_email(e)
        sd_count = sum(1 for l in found if is_sd_market(l.get("address", "")))
        print(f"  Parsed {len(found)} listing(s) ({sd_count} SD) from: {e['subject'][:55]}")
        for l in found:
            sf_str  = f"  {l['sf']:,} SF"    if l["sf"]    else ""
            ac_str  = f"  {l['acres']} AC"   if l["acres"] else ""
            cr_str  = f"  Cap {l['cap_rate']:.1f}%" if l["cap_rate"] else ""
            print(f"    {l['type']:22}  {l['price_display']:>14}{sf_str}{ac_str}{cr_str}")
            print(f"      {l['address']}")
        all_listings.extend(found)

    if not all_listings:
        print("\nEmails found but no individual listings could be parsed.")
        print("Run --check and compare the email body format.")
        print("You can also forward a sample LoopNet alert to check parsing.")
        return

    write_loopnet_js(all_listings)

    if args.email:
        send_email_summary(all_listings)

    # Print summary
    summary = build_summary(all_listings)
    print(f"\n── Summary ───────────────────────────────────────────")
    print(f"   Total listings parsed:  {summary['total']}")
    for t, n in sorted(summary["by_type"].items(), key=lambda x: -x[1]):
        print(f"   {t:30} {n}")
    if summary["avg_price"]:
        print(f"\n   Avg price:   ${summary['avg_price']:,}")
        print(f"   Price range: ${summary['price_range']['min']:,} – ${summary['price_range']['max']:,}")
    print()


if __name__ == "__main__":
    main()
