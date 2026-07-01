#!/usr/bin/env python3
"""
Paragon Inbox Parser — Kevin Andreson / Keller Williams Black Hills
Reads arecblackhills@gmail.com, finds Paragon Collaboration Center emails,
extracts individual listings, then:
  1. Writes aggregated counts to js/market-data.js (MLS detail table)
  2. Writes individual listing cards to js/paragon-listings.js

Usage:
  python3 parse_paragon_inbox.py          # parse + update both JS files
  python3 parse_paragon_inbox.py --check  # show emails found, no write
  python3 parse_paragon_inbox.py --days 30  # look back 30 days (default: 14)
"""
import argparse, email, imaplib, json, os, re, sys, time
from datetime import datetime, timedelta
from email.header import decode_header
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(__file__))
from config import FROM_EMAIL, GMAIL_APP_PASSWORD, IMAP_EMAIL, IMAP_APP_PASSWORD, PRICE_BANDS, MLS_DETAIL_CATEGORIES

MARKET_DATA_JS   = os.path.join(os.path.dirname(__file__), '..', '..', 'js', 'market-data.js')
LISTINGS_JS      = os.path.join(os.path.dirname(__file__), '..', '..', 'js', 'paragon-listings.js')
PHOTOS_CACHE     = os.path.join(os.path.dirname(__file__), 'photos-cache.json')
PHOTOS_DIR       = os.path.join(os.path.dirname(__file__), '..', '..', 'img', 'listings')
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# ── Property type → MLS detail category ──────────────────────────────────────
PROP_TYPE_MAP = {
    "site built":           "Residential Resale (Single Family)",
    "single family":        "Residential Resale (Single Family)",
    "condo":                "Residential Resale (Single Family)",
    "townhouse":            "Residential Resale (Single Family)",
    "manufactured":         "Residential Resale (Single Family)",
    "modular":              "Residential Resale (Single Family)",
    "residential":          "Residential Resale (Single Family)",
    "multi-family":         "Commercial — Multi-Family",
    "multi family":         "Commercial — Multi-Family",
    "multifamily":          "Commercial — Multi-Family",
    "duplex":               "Commercial — Multi-Family",
    "triplex":              "Commercial — Multi-Family",
    "apartment":            "Commercial — Multi-Family",
    "industrial":           "Commercial — Industrial",
    "warehouse":            "Commercial — Industrial",
    "flex":                 "Commercial — Industrial",
    "general commercial":   "Commercial — General Commercial",
    "commercial":           "Commercial — General Commercial",
    "retail":               "Commercial — General Commercial",
    "office":               "Commercial — General Commercial",
    "land":                 "Commercial — General Commercial",
    "lot":                  "Commercial — General Commercial",
    "acreage":              "Commercial — General Commercial",
}

# ── Status normalizer ─────────────────────────────────────────────────────────
def normalize_status(raw):
    r = raw.lower().strip()
    if "under contract" in r or "pending" in r or "contingent" in r:
        return "Under Contract"
    if "sold" in r or "closed" in r:
        return "Sold"
    if "active" in r or "new" in r:
        return "Active"
    return None


# ── HTML parser — extracts text lines AND links in document order ─────────────
class ParagonEmailParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._text  = []
        self._links = []
        self._current_href = None
        self._skip = False

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "style":
            self._skip = True
        if tag == "a":
            href = d.get("href", "")
            if href.startswith("http"):
                self._current_href = href
                self._links.append(href)
        if tag in ("br","p","tr","div","td","li","h1","h2","h3","h4"):
            self._text.append("\n")

    def handle_endtag(self, tag):
        if tag == "style":
            self._skip = False
        if tag == "a":
            self._current_href = None
        if tag in ("p","tr","div","td","li","h1","h2","h3","h4"):
            self._text.append("\n")

    def handle_data(self, d):
        if self._skip:
            return
        stripped = d.strip()
        if stripped and not re.match(r'^[\s{};:]+$', stripped):
            self._text.append(stripped)

    def get_text(self):
        return "\n".join(t for t in self._text if t.strip())

    def get_links(self):
        return self._links


def decode_str(s):
    if not s: return ""
    parts = decode_header(s)
    out = []
    for part, enc in parts:
        if isinstance(part, bytes):
            out.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(part)
    return " ".join(out)


def get_body_links_and_view_links(msg):
    """
    Returns (body_text, all_links, view_this_listing_links).
    view_this_listing_links: ordered list of DetailTokenLogon hrefs, one per
    'View This Listing' occurrence, taken from the <a> tag wrapping that text.
    """
    html_body = ""
    for part in msg.walk():
        ct = part.get_content_type()
        cd = str(part.get("Content-Disposition", ""))
        if "attachment" in cd:
            continue
        if ct == "text/html":
            try:
                html_body += part.get_payload(decode=True).decode("utf-8", errors="replace")
            except Exception:
                pass

    if html_body:
        p = ParagonEmailParser()
        p.feed(html_body)
        body_text = p.get_text()
        all_links = p.get_links()

        # For each "View This Listing" in the raw HTML, get the nearest
        # DetailTokenLogon href immediately preceding it (its own <a> tag)
        view_links = []
        for m in re.finditer(r'(?i)view\s+this\s+listing', html_body):
            before = html_body[max(0, m.start()-800):m.start()]
            found = re.findall(r'href=["\']([^"\']*DetailTokenLogon[^"\']*)["\']', before)
            view_links.append(found[-1] if found else None)

        return body_text, all_links, view_links

    # Plain text fallback
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            try:
                return part.get_payload(decode=True).decode("utf-8", errors="replace"), [], []
            except Exception:
                pass
    return "", [], []

def get_body_and_links(msg):
    body, links, _ = get_body_links_and_view_links(msg)
    return body, links


# ── IMAP connection ───────────────────────────────────────────────────────────
def connect():
    if IMAP_APP_PASSWORD.strip():
        try:
            m = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            m.login(IMAP_EMAIL, IMAP_APP_PASSWORD)
            print(f"✓ Connected to {IMAP_EMAIL}")
            return m
        except imaplib.IMAP4.error as e:
            print(f"  arecblackhills login failed ({e}) — falling back to {FROM_EMAIL}")
    try:
        m = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        m.login(FROM_EMAIL, GMAIL_APP_PASSWORD)
        print(f"✓ Connected to {FROM_EMAIL}")
        return m
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
            date_str = msg.get("Date", "")

            if not _is_paragon(sender, subject):
                continue

            body, links, view_links = get_body_links_and_view_links(msg)

            # Extract saved search name from subject or body
            search_name = ""
            for line in body.splitlines():
                line = line.strip()
                if line and len(line) < 80 and not any(k in line.lower() for k in
                    ("collaboration", "notification", "visit", "update", "unsubscribe",
                     "contact", "kevin", "keller", "ames", "spearfish")):
                    # First meaningful short line is usually the search name
                    if re.search(r'\$|residential|commercial|industrial|land|bedroom|bd', line, re.IGNORECASE):
                        search_name = line
                        break

            results.append({
                "sender":      sender,
                "subject":     subject,
                "date":        date_str,
                "body":        body,
                "links":       links,
                "view_links":  view_links,  # per-listing DetailTokenLogon links in order
                "search_name": search_name,
            })
        break
    return results


def _is_paragon(sender, subject):
    sl = sender.lower(); su = subject.lower()
    if "kandreson@kw.com" in sl:
        return False
    return (
        any(k in sl for k in ("paragonmessaging", "paragonrels", "paragon", "bhrealtors", "mtrushmoremls", "blackhillsrealtors"))
        or any(k in su for k in ("collaboration center", "saved search", "new listing", "mls alert", "search update", "activity notification"))
    )


# ── Individual listing extractor ──────────────────────────────────────────────
def parse_listings(email_data):
    """
    Extract individual listings from a Paragon Collaboration Center email.
    Returns list of full listing dicts.

    Format in these emails:
      Status line  (Active - ACTIVE / New)
      "View This Listing"
      Street address
      City, State ZIP
      "MLS #"
      MLS number
      Property type  (Site Built / General Commercial / etc.)
      Price  ($395,000)
    """
    body        = email_data["body"]
    links       = email_data["links"]
    view_links  = email_data.get("view_links", [])  # per-listing links in document order
    date_raw    = email_data["date"]
    search_name = email_data.get("search_name", "")

    try:
        from email.utils import parsedate_to_datetime
        alert_dt   = parsedate_to_datetime(date_raw)
        alert_date = alert_dt.strftime("%Y-%m-%d")
    except Exception:
        alert_date = datetime.now().strftime("%Y-%m-%d")

    # DetailTokenLogon links = individual property links
    detail_links = [l for l in links if "DetailToken" in l or "detail" in l.lower()]

    lines = [l.strip() for l in body.splitlines() if l.strip()]
    listings = []

    i = 0
    while i < len(lines):
        line = lines[i]
        status = normalize_status(line)
        if status is None:
            i += 1
            continue

        # Look ahead up to 12 lines
        window = lines[i:min(i+12, len(lines))]

        address    = None
        city_state = None
        mls_num    = None
        prop_type  = None
        price      = None
        view_link  = None

        j = 0
        while j < len(window):
            wl = window[j]

            # "View This Listing" — use the pre-matched per-listing link (in order)
            if "view this listing" in wl.lower():
                idx = len(listings)  # number of listings already completed
                if view_links and idx < len(view_links) and view_links[idx]:
                    view_link = view_links[idx]
                elif detail_links:
                    view_link = detail_links[idx % max(len(detail_links), 1)]

            # MLS number — line after "MLS #"
            if wl.strip() == "MLS #" and j + 1 < len(window):
                mls_num = window[j+1].strip()
                j += 2
                continue

            # Price
            if price is None:
                pm = re.match(r'^\$[\d,]+$', wl)
                if pm:
                    price = int(re.sub(r'[^\d]', '', wl))

            # Property type
            if prop_type is None:
                wll = wl.lower()
                for key, cat in PROP_TYPE_MAP.items():
                    if key in wll and len(wl) < 40:
                        prop_type = cat
                        break

            # City/State line (contains ", SD" or state abbrev)
            if city_state is None and re.search(r',\s*[A-Z]{2}\s+\d{5}', wl):
                city_state = wl

            # Street address — line before city/state, has digits
            if city_state and address is None:
                idx = window.index(wl) if wl in window else j
                if idx > 0:
                    prev = window[idx-1]
                    if re.match(r'^\d+\s+\w', prev) and len(prev) < 60:
                        address = prev

            j += 1

        # Also try to find address directly if not found via city_state
        if address is None:
            for wl in window:
                if re.match(r'^\d+\s+\w', wl) and len(wl) < 60 and not re.search(r'\$', wl):
                    address = wl
                    break

        if price is None or price < 50_000:
            i += 1
            continue

        # Deduplicate
        key = (address, price)
        if any((l.get("address"), l.get("price")) == key for l in listings):
            i += 10
            continue

        listings.append({
            "status":      status,
            "address":     address or "Address not parsed",
            "city_state":  city_state or "",
            "full_address": (address or "") + (", " + city_state if city_state else ""),
            "mls_num":     mls_num,
            "prop_type":   prop_type or "Residential Resale (Single Family)",
            "price":       price,
            "price_display": "$" + f"{price:,}",
            "paragon_url": view_link,
            "alert_date":  alert_date,
            "search_name": search_name,
        })
        i += 10

    return listings


# ── Aggregation for MLS detail table ─────────────────────────────────────────
def bucket_price(price):
    for label, lo, hi in PRICE_BANDS:
        if lo <= price < hi:
            return label
    return None


def aggregate(all_listings):
    detail = {}
    for cat in MLS_DETAIL_CATEGORIES:
        detail[cat] = {}
        for band, _, _ in PRICE_BANDS:
            detail[cat][band] = {"Active": 0, "Under Contract": 0, "Sold": 0}

    for lst in all_listings:
        cat    = lst["prop_type"]
        band   = bucket_price(lst["price"])
        status = lst["status"]
        if cat in detail and band and band in detail[cat] and status in detail[cat][band]:
            detail[cat][band][status] += 1

    for cat in detail:
        for band in detail[cat]:
            for s in detail[cat][band]:
                if detail[cat][band][s] == 0:
                    detail[cat][band][s] = None
    return detail


# ── Write market-data.js ──────────────────────────────────────────────────────
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
        f"// Auto-generated by parse_paragon_inbox.py — {datetime.now().strftime('%B %d, %Y')}\n"
        f"window.MARKET_DATA = {json.dumps(data, indent=2)};\n"
    )
    with open(MARKET_DATA_JS, 'w') as f:
        f.write(new_content)
    print(f"✓ market-data.js updated")


# ── Write paragon-listings.js ─────────────────────────────────────────────────
def write_listings_js(all_listings):
    # Deduplicate by (address, price) across all emails
    seen = set()
    unique = []
    for l in all_listings:
        k = (l["address"], l["price"])
        if k not in seen:
            seen.add(k)
            unique.append(l)

    # Sort newest first
    unique.sort(key=lambda x: x["alert_date"], reverse=True)

    by_type = {}
    for l in unique:
        t = l["prop_type"]
        by_type[t] = by_type.get(t, 0) + 1

    prices = [l["price"] for l in unique]
    summary = {
        "total":       len(unique),
        "by_type":     by_type,
        "avg_price":   int(sum(prices)/len(prices)) if prices else None,
        "price_range": {"min": min(prices) if prices else None, "max": max(prices) if prices else None},
    }

    data = {
        "generated": datetime.now().strftime("%B %d, %Y at %I:%M %p"),
        "listings":  unique,
        "summary":   summary,
    }
    content = (
        f"// Auto-generated by parse_paragon_inbox.py — {datetime.now().strftime('%B %d, %Y')}\n"
        f"window.PARAGON_LISTINGS = {json.dumps(data, indent=2)};\n"
    )
    with open(LISTINGS_JS, 'w') as f:
        f.write(content)
    print(f"✓ paragon-listings.js updated — {len(unique)} unique listings")
    return unique


# ── Paragon photo scraper (Playwright headless browser) ──────────────────────
def load_photos_cache():
    if os.path.exists(PHOTOS_CACHE):
        try:
            with open(PHOTOS_CACHE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_photos_cache(cache):
    with open(PHOTOS_CACHE, 'w') as f:
        json.dump(cache, f, indent=2)

PARAGON_PLACEHOLDER_KEYWORDS = [
    'neighborhood', 'sunsetneighborhood', 'static/', 'noimage', 'no_image',
    'placeholder', 'blank.', 'default.', 'missing',
]

def _upscale_paragon_url(url):
    """
    Paragon thumbnail URLs contain width/height segments like /120/90/.
    Replace with a large size to get the full-res version.
    e.g. /Property/PC/GBHAR/89277/6/120/90/hash → /Property/PC/GBHAR/89277/6/800/600/hash
    """
    m = re.search(r'(ParagonImages/Property/[^/]+/[^/]+/\d+/\d+)/\d+/\d+/', url)
    if m:
        return url[:m.start(1) + len(m.group(1))] + '/800/600/' + url[url.index('/', m.start(1) + len(m.group(1)) + 1) + 1:]
    return url

def _is_placeholder(url):
    low = url.lower()
    return any(k in low for k in PARAGON_PLACEHOLDER_KEYWORDS)

def _best_photo_from_page(page, mls_num=None):
    """
    Extract the best property photo URL from a rendered Paragon listing page.
    If mls_num is given, prefer photos whose URL contains that MLS number.
    """
    try:
        page.wait_for_selector('img', timeout=10000)
    except Exception:
        pass

    try:
        page.evaluate("window.scrollBy(0, 400)")
        time.sleep(0.8)
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.4)
    except Exception:
        pass

    try:
        all_imgs = page.evaluate("""
            (placeholders) => {
                const imgs = [...document.querySelectorAll('img')];
                const out  = [];
                for (const img of imgs) {
                    const src = img.src || img.getAttribute('src') || '';
                    if (!src.startsWith('http')) continue;
                    const low = src.toLowerCase();
                    if (['icon','logo','avatar','sprite','button','kw.com','kellerwilliams','blank.'].some(s => low.includes(s))) continue;
                    if (placeholders.some(p => low.includes(p))) continue;
                    const r = img.getBoundingClientRect();
                    if (r.width > 60 && r.height > 50) out.push({src, area: r.width * r.height});
                }
                return out;
            }
        """, PARAGON_PLACEHOLDER_KEYWORDS)
    except Exception:
        all_imgs = []

    if all_imgs:
        # Prefer photos that contain the correct MLS number in the URL
        if mls_num:
            mls_matches = [i for i in all_imgs if mls_num in i['src']]
            if mls_matches:
                best = max(mls_matches, key=lambda x: x['area'])
                return _upscale_paragon_url(best['src'])
        # Otherwise take the largest
        best = max(all_imgs, key=lambda x: x['area'])
        if not _is_placeholder(best['src']):
            return _upscale_paragon_url(best['src'])

    return None

MLS_IN_URL_RE = re.compile(r'/ParagonImages/Property/[^/]+/[^/]+/(\d{4,6})/')

def _on_photo_response(response, photo_bank):
    """Shared response handler: extract MLS# from CDN URL and store bytes."""
    url = response.url
    if 'zimg.paragon.ice.com/ParagonImages/Property' not in url:
        return
    low = url.lower()
    if any(k in low for k in PARAGON_PLACEHOLDER_KEYWORDS):
        return
    m = MLS_IN_URL_RE.search(url)
    if not m:
        return
    url_mls = m.group(1)
    try:
        body = response.body()
        if len(body) < 3000:
            return
        if url_mls not in photo_bank or len(body) > len(photo_bank[url_mls][1]):
            photo_bank[url_mls] = (url, body)
    except Exception:
        pass

def _load_page_into_bank(paragon_url, page, photo_bank):
    """
    Navigate to paragon_url. Capture every Paragon CDN photo response.
    Also scrape CCR sidebar listing links and click through them so we
    capture photos for all listings in the same batch email.
    """
    handler = lambda r: _on_photo_response(r, photo_bank)
    page.on('response', handler)
    try:
        page.goto(paragon_url, wait_until='networkidle', timeout=30000)
    except Exception:
        try:
            page.goto(paragon_url, wait_until='domcontentloaded', timeout=20000)
            time.sleep(4)
        except Exception:
            pass

    # Find all CCR listing links in the sidebar and click through each one
    # to capture photos for every listing in this batch
    try:
        sidebar_links = page.evaluate("""() => {
            const seen = new Set();
            const out  = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const h = a.href;
                if (h.includes('DetailTokenLogon') || h.includes('/CollabLink/')) {
                    if (!seen.has(h)) { seen.add(h); out.push(h); }
                }
            });
            return out;
        }""")
        for link in sidebar_links[1:12]:  # skip first (current page), visit up to 11 more
            try:
                page.goto(link, wait_until='networkidle', timeout=20000)
            except Exception:
                try:
                    page.goto(link, wait_until='domcontentloaded', timeout=15000)
                    time.sleep(3)
                except Exception:
                    pass
    except Exception:
        pass

    page.remove_listener('response', handler)

def enrich_with_photos(listings, skip_photos=False):
    """
    Add photo_url to each listing.
    Strategy: visit every unique Paragon URL; every page load captures photos for the
    main listing AND all sidebar thumbnails (each has its MLS# in the CDN URL).
    Build a global photo_bank keyed by MLS number, then assign.
    """
    if skip_photos:
        for l in listings:
            l['photo_url'] = None
        return listings

    cache = load_photos_cache()  # mls_num -> local_path (from previous runs)

    # Listings already in photo cache (by mls_num)
    mls_in_cache = set(cache.keys())
    need_mls     = {l['mls_num'] for l in listings if l.get('mls_num') and l['mls_num'] not in mls_in_cache}

    # Unique URLs we haven't visited yet — deduplicated
    visited_urls = cache.get('__visited_urls__', [])
    all_urls     = list({l['paragon_url'] for l in listings if l.get('paragon_url')})
    to_visit     = [u for u in all_urls if u not in visited_urls]

    os.makedirs(PHOTOS_DIR, exist_ok=True)
    photo_bank = {}  # mls_num -> (url, bytes) — built during this run

    if to_visit:
        print(f"  Visiting {len(to_visit)} unique Paragon URLs (capturing all photos seen)...")
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                ctx = browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                )
                for i, url in enumerate(to_visit, 1):
                    page = ctx.new_page()
                    try:
                        _load_page_into_bank(url, page, photo_bank)
                    finally:
                        page.close()
                    visited_urls.append(url)
                    if i % 5 == 0:
                        print(f"    {i}/{len(to_visit)} pages loaded, {len(photo_bank)} MLS photos captured...")
                browser.close()
        except Exception as e:
            print(f"  Playwright error: {e}")

    # Save captured photo files and update cache
    newly_saved = 0
    for mls_num, (photo_url, img_bytes) in photo_bank.items():
        if mls_num in cache:
            continue  # already have a saved photo for this listing
        fname = f"{mls_num}.jpg"
        fpath = os.path.join(PHOTOS_DIR, fname)
        with open(fpath, 'wb') as f:
            f.write(img_bytes)
        cache[mls_num] = f"../img/listings/{fname}"
        newly_saved += 1

    cache['__visited_urls__'] = visited_urls
    save_photos_cache(cache)

    # Assign photo_url to each listing by MLS number
    for l in listings:
        mls = l.get('mls_num', '')
        l['photo_url'] = cache.get(mls) or None

    found = sum(1 for l in listings if l.get('photo_url'))
    print(f"✓ Photos: {found}/{len(listings)} ({newly_saved} newly saved)")
    return listings


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check",       action="store_true", help="Show emails, no write")
    ap.add_argument("--days",        type=int, default=14, help="Days back (default: 14)")
    ap.add_argument("--no-photos",   action="store_true", help="Skip Paragon photo fetching")
    args = ap.parse_args()

    inbox = IMAP_EMAIL if IMAP_APP_PASSWORD.strip() else FROM_EMAIL
    print(f"\nConnecting to {inbox}...")
    mail = connect()
    print()

    print(f"Searching last {args.days} days for Paragon emails...")
    paragon_emails = fetch_paragon_emails(mail, days=args.days)
    mail.logout()
    print(f"✓ Found {len(paragon_emails)} Paragon email(s)\n")

    for e in paragon_emails:
        label = e["search_name"] or e["subject"]
        print(f"  · {e['date'][:16]}  |  {label[:65]}")

    if args.check or not paragon_emails:
        if not paragon_emails:
            print("\nNo Paragon emails found. Check saved search email settings in Paragon.")
        return

    all_listings = []
    for e in paragon_emails:
        found = parse_listings(e)
        label = e["search_name"] or e["subject"][:45]
        print(f"\n  {len(found)} listing(s) from: {label}")
        for lst in found:
            band = bucket_price(lst["price"])
            print(f"    {lst['status']:15}  {lst['price_display']:>12}  ({band or 'below min'})")
            print(f"      {lst['full_address']}  |  {lst['prop_type']}  |  MLS {lst['mls_num'] or '?'}")
        all_listings.extend(found)

    if not all_listings:
        print("\nEmails found but no listings parsed. Run --check to inspect email format.")
        return

    print(f"\nFetching Paragon listing photos...")
    all_listings = enrich_with_photos(all_listings, skip_photos=args.no_photos)

    detail = aggregate(all_listings)
    update_market_data(detail)
    unique = write_listings_js(all_listings)

    total = sum(
        v for cat in detail.values()
        for band in cat.values()
        for v in band.values() if v
    )
    print(f"\n✓ Done — {len(unique)} unique listings | {total} non-empty MLS table cells")


if __name__ == "__main__":
    main()
