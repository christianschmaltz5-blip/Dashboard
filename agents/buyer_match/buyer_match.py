#!/usr/bin/env python3
"""
Buyer-match daily job (v2) — Kevin Andreson / KW Black Hills

When a new MLS listing fits a saved buyer's criteria, draft the "thought of you"
email automatically and drop it in Kevin's Gmail Drafts folder for review. Runs
after the 6am Paragon sync; only ever DRAFTS — never sends.

Pipeline:
  buyers.json  ─┐
                ├─► score each buyer × listing (budget / type / area / recency)
  listings ─────┘        └─► keep only NEW matches (not in alerted.json)
                              └─► Claude drafts the email
                                   └─► IMAP APPEND to Gmail "Drafts"

Buyer data (no re-typing): either
  • export from the Buyer Match web page  → buyers.json, or
  • python3 buyer_match.py --import-csv <KWCommandExport.csv>   (KW Command → buyers.json)

Secrets: IMAP creds are reused from ../mls_report/config.py (not duplicated).
The Anthropic key is read from the ANTHROPIC_API_KEY env var (never hardcoded);
without it, the job falls back to a plain template email.

Usage:
  python3 buyer_match.py                 # find new matches, create Gmail drafts
  python3 buyer_match.py --dry-run       # show what it would draft, create nothing
  python3 buyer_match.py --import-csv contacts.csv
  python3 buyer_match.py --limit 10 --no-ai
"""

import argparse
import imaplib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from email.message import EmailMessage

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
BUYERS_PATH = os.path.join(HERE, "buyers.json")
STATE_PATH = os.path.join(HERE, "alerted.json")
LISTINGS_JS = os.path.join(REPO, "js", "paragon-listings.js")

# Reuse the Paragon inbox's IMAP creds / addresses — single source of secrets.
sys.path.insert(0, os.path.join(REPO, "agents", "mls_report"))
try:
    import config as CFG
except Exception:
    CFG = None

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = "claude-sonnet-4-6"
DRAFTS_FOLDER = '"[Gmail]/Drafts"'
TOP_PER_BUYER = 6

AGENT = {"name": "Kevin Andreson", "firm": "Keller Williams Realty Black Hills",
         "phone": "605-646-5409", "email": "arecblackhills@gmail.com"}


# ── Load buyers + listings ───────────────────────────────────────────────────
def load_buyers():
    if not os.path.exists(BUYERS_PATH):
        return []
    with open(BUYERS_PATH) as f:
        return json.load(f)


def load_listings():
    """Read window.PARAGON_LISTINGS = {…}; out of the generated JS file."""
    if not os.path.exists(LISTINGS_JS):
        return []
    txt = open(LISTINGS_JS).read()
    m = re.search(r"window\.PARAGON_LISTINGS\s*=\s*(\{[\s\S]*\});", txt)
    if not m:
        return []
    return json.loads(m.group(1)).get("listings", [])


def load_state():
    if not os.path.exists(STATE_PATH):
        return set()
    try:
        return set(json.load(open(STATE_PATH)).get("alerted", []))
    except Exception:
        return set()


def save_state(alerted):
    with open(STATE_PATH, "w") as f:
        json.dump({"alerted": sorted(alerted),
                   "updated": datetime.now(timezone.utc).isoformat(timespec="seconds")}, f, indent=2)


# ── Scoring (mirrors pages/buyer-match.html) ─────────────────────────────────
def parse_budget(s):
    if not s:
        return None
    s = str(s).lower().replace(",", "")
    nums = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(k|m)?", s):
        n = float(m.group(1))
        suf = m.group(2)
        if suf == "k":
            n *= 1e3
        elif suf == "m":
            n *= 1e6
        elif n < 10000:            # bare shorthand: 400 -> 400k
            n *= 1e3
        if n >= 1000:
            nums.append(n)
    if not nums:
        return None
    nums.sort()
    if len(nums) == 1:
        return {"min": nums[0] * 0.6, "max": nums[0]}
    return {"min": nums[0], "max": nums[-1]}


def cat_of(t):
    t = (t or "").lower()
    if re.search(r"single family|residential|condo|townhouse|duplex|home", t):
        return "residential"
    if re.search(r"commercial|office|retail|industrial", t):
        return "commercial"
    if re.search(r"land|lot|acre", t):
        return "land"
    return "other"


def wanted_cat(txt):
    txt = (txt or "").lower()
    if re.search(r"commercial|office|retail|industrial", txt):
        return "commercial"
    if re.search(r"\b(land|lot|acre|acreage|farm|ranch)\b", txt):
        return "land"
    if re.search(r"residential|home|house|single family|family home|bed", txt):
        return "residential"
    return None


def _city_of(cs):
    return (cs or "").split(",")[0].strip().lower()


def score_match(buyer, listing):
    if (buyer.get("type") or "").lower() == "seller":
        return None
    if (listing.get("status") or "").lower() == "sold":
        return None
    reasons = []
    score = 0

    bud = parse_budget(buyer.get("budget"))
    price = listing.get("price")
    if bud and price:
        if bud["min"] <= price <= bud["max"]:
            score += 50
            reasons.append("In budget")
        elif bud["max"] < price <= bud["max"] * 1.1:
            score += 25
            reasons.append("~10% over budget")
        else:
            return None

    want = wanted_cat((buyer.get("interest") or "") + " " + (buyer.get("notes") or ""))
    cat = cat_of(listing.get("prop_type"))
    if want:
        if want == cat:
            score += 25
            reasons.append(want.capitalize())
        elif cat != "other":
            return None

    bcity = _city_of(buyer.get("city"))
    lcity = _city_of(listing.get("city_state"))
    if bcity and lcity:
        if bcity in lcity:
            score += 30
            reasons.append("In " + lcity.title())
        else:
            reasons.append("outside " + bcity.title())

    ad = listing.get("alert_date")
    if ad:
        try:
            days = (datetime.now() - datetime.strptime(ad, "%Y-%m-%d")).days
            if days <= 7:
                score += 10
                reasons.append("New this week")
        except ValueError:
            pass
    if score < 25:
        return None
    return {"score": score, "reasons": reasons}


def buyer_key(b):
    return f"{b.get('firstName','')}|{b.get('lastName','')}|{b.get('email','')}"


def find_matches(buyers, listings):
    """Return list of dicts {buyer, listing, score, reasons}, each buyer's top N."""
    out = []
    for b in buyers:
        hits = []
        for l in listings:
            s = score_match(b, l)
            if s:
                hits.append({"buyer": b, "listing": l, **s})
        hits.sort(key=lambda x: x["score"], reverse=True)
        out.extend(hits[:TOP_PER_BUYER])
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


# ── Email drafting ───────────────────────────────────────────────────────────
def sig():
    return f"\n\n{AGENT['name']}\n{AGENT['firm']}\n{AGENT['phone']}\n{AGENT['email']}"


def draft_with_ai(buyer, listing):
    if not ANTHROPIC_KEY:
        return None
    wants = "; ".join(x for x in [
        buyer.get("interest"),
        f"budget {buyer['budget']}" if buyer.get("budget") else "",
        f"area {buyer['city']}" if buyer.get("city") else "",
        buyer.get("timeline"), buyer.get("notes")] if x) or "general home search"
    prompt = f"""You are writing a short "thought of you" email for {AGENT['name']}, a real estate agent at {AGENT['firm']} in Rapid City, SD, to a buyer client about a new listing that fits what they want.

BUYER: {buyer.get('firstName','')} {buyer.get('lastName','')}
What they want: {wants}

NEW LISTING:
{listing.get('full_address') or listing.get('address')} — {listing.get('price_display')} — {listing.get('prop_type')} (MLS {listing.get('mls_num')})

Write a warm, brief, personal email (2 short paragraphs). Reference specifically why this fits what THEY told you they wanted. Not salesy. Offer to send details or set up a showing. Do not invent property features you were not given.

Return JSON only: {{ "subject": "...", "body": "..." }}"""
    try:
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=40,
                          headers={"content-type": "application/json", "x-api-key": ANTHROPIC_KEY,
                                   "anthropic-version": "2023-06-01"},
                          json={"model": ANTHROPIC_MODEL, "max_tokens": 600,
                                "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        raw = r.json()["content"][0]["text"].strip()
        mt = re.search(r"\{[\s\S]*\}", raw)
        d = json.loads(mt.group(0)) if mt else None
        if d and d.get("subject") and d.get("body"):
            return {"subject": d["subject"], "body": d["body"] + sig()}
    except Exception as e:
        print(f"    (AI draft failed, using template: {e})")
    return None


def draft_template(buyer, listing):
    first = buyer.get("firstName") or "there"
    addr = listing.get("full_address") or listing.get("address")
    body = (f"Hi {first},\n\nA new listing just came up that made me think of you — "
            f"{addr}, listed at {listing.get('price_display')} ({listing.get('prop_type')}). "
            f"It looks like a fit for what you're after"
            + (f" ({buyer.get('interest')})" if buyer.get("interest") else "") + ".\n\n"
            "Want me to send over the full details or set up a time to see it?" + sig())
    return {"subject": f"Thought of you — {addr}", "body": body}


def build_draft(buyer, listing, use_ai=True):
    return (use_ai and draft_with_ai(buyer, listing)) or draft_template(buyer, listing)


# ── Gmail draft creation (IMAP APPEND) ───────────────────────────────────────
def imap_creds():
    if CFG is None:
        return None
    email = (getattr(CFG, "IMAP_EMAIL", "") or getattr(CFG, "TO_EMAIL", "")).strip()
    pwd = (getattr(CFG, "IMAP_APP_PASSWORD", "") or getattr(CFG, "GMAIL_APP_PASSWORD", "")).strip()
    host = getattr(CFG, "IMAP_HOST", "imap.gmail.com")
    port = getattr(CFG, "IMAP_PORT", 993)
    return (email, pwd, host, port) if email and pwd else None


def create_gmail_draft(to_email, to_name, subject, body, creds):
    email_addr, pwd, host, port = creds
    msg = EmailMessage()
    msg["From"] = f"{AGENT['name']} <{AGENT['email']}>"
    msg["To"] = f"{to_name} <{to_email}>" if to_email else to_name
    msg["Subject"] = subject
    msg.set_content(body)
    m = imaplib.IMAP4_SSL(host, port)
    m.login(email_addr, pwd)
    try:
        m.append(DRAFTS_FOLDER, "\\Draft", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
    finally:
        try:
            m.logout()
        except Exception:
            pass


# ── KW Command CSV import ────────────────────────────────────────────────────
def import_csv(path):
    import csv
    if not os.path.exists(path):
        print(f"CSV not found: {path}")
        sys.exit(1)
    aliases = {
        "firstName": ["first name", "first"], "lastName": ["last name", "last"],
        "email": ["email"], "phone": ["phone"], "city": ["city"], "state": ["state"],
        "type": ["lead type", "type"], "source": ["lead source", "source"],
        "stage": ["stage"], "timeline": ["timeline"],
        "budget": ["budget", "price range", "budget / price range"],
        "interest": ["property interest", "interest"], "notes": ["notes"],
    }
    buyers = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if len(rows) < 2:
        print("CSV needs a header row plus at least one contact.")
        sys.exit(1)
    header = [h.strip().lower() for h in rows[0]]

    def col(field):
        for a in aliases[field]:
            if a in header:
                return header.index(a)
        return -1

    idx = {k: col(k) for k in aliases}
    for row in rows[1:]:
        if not row:
            continue
        def g(k):
            return row[idx[k]].strip() if idx[k] >= 0 and idx[k] < len(row) else ""
        if not (g("firstName") or g("lastName")):
            continue
        buyers.append({k: g(k) for k in aliases} | {"tags": [], "addedDate": "imported"})
    with open(BUYERS_PATH, "w") as f:
        json.dump(buyers, f, indent=2)
    print(f"✓ Imported {len(buyers)} buyers → {BUYERS_PATH}")


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Daily buyer-match → Gmail drafts")
    ap.add_argument("--dry-run", action="store_true", help="print matches, create no drafts, don't update state")
    ap.add_argument("--import-csv", metavar="FILE", help="import buyers from a KW Command CSV and exit")
    ap.add_argument("--limit", type=int, default=25, help="max drafts to create this run (default 25)")
    ap.add_argument("--no-ai", action="store_true", help="skip Claude, use the plain template email")
    args = ap.parse_args()

    if args.import_csv:
        import_csv(args.import_csv)
        return

    buyers = load_buyers()
    listings = load_listings()
    if not buyers:
        print(f"No buyers in {BUYERS_PATH}. Export from the Buyer Match page or --import-csv a KW Command file.")
        return
    if not listings:
        print(f"No listings found in {LISTINGS_JS}. Has the Paragon sync run?")
        return

    matches = find_matches(buyers, listings)
    alerted = load_state()
    new = [m for m in matches
           if f"{buyer_key(m['buyer'])}#{m['listing'].get('mls_num')}" not in alerted]

    print(f"{len(buyers)} buyers × {len(listings)} listings → {len(matches)} matches, {len(new)} new")
    if not new:
        return

    creds = imap_creds()
    if not creds and not args.dry_run:
        print("No IMAP creds in config.py — can't create Gmail drafts. Run with --dry-run to preview.")
        return

    created = 0
    for m in new[:args.limit]:
        b, l = m["buyer"], m["listing"]
        name = f"{b.get('firstName','')} {b.get('lastName','')}".strip()
        tag = f"{name} ← {l.get('price_display')} {l.get('address')} [{m['score']}] {', '.join(m['reasons'])}"
        if args.dry_run:
            print("  DRY  " + tag)
            continue
        if not b.get("email"):
            print("  SKIP (no email) " + tag)
            continue
        d = build_draft(b, l, use_ai=not args.no_ai)
        try:
            create_gmail_draft(b["email"], name, d["subject"], d["body"], creds)
            alerted.add(f"{buyer_key(b)}#{l.get('mls_num')}")
            created += 1
            print("  DRAFT " + tag)
        except Exception as e:
            print(f"  FAIL  {tag}  ({e})")

    if not args.dry_run:
        save_state(alerted)
        print(f"\n✓ {created} draft(s) created in {AGENT['email']} → Drafts. Review and send.")


if __name__ == "__main__":
    main()
