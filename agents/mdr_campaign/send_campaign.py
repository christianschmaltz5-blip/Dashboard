#!/usr/bin/env python3
"""
MDR Land Marketing Campaign — Kevin Andreson / Keller Williams Black Hills
Generates a sophisticated first-touch outreach email for the MDR development
site (Highway 1416, Box Elder SD) using Claude, then sends a preview to Kevin
for review. Kevin sends the final email manually.

Usage:
  python3 send_campaign.py           # generate + send preview to Kevin
  python3 send_campaign.py --draft   # print draft only, no email
"""
import argparse, os, smtplib, sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hwy1416_newsletter'))
from config import FROM_EMAIL, GMAIL_APP_PASSWORD, REPLY_TO

try:
    import anthropic
except ImportError:
    print("Run: pip install anthropic")
    sys.exit(1)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── Property details ──────────────────────────────────────────────────────────
PROPERTY = {
    "name":     "MDR Development",
    "address":  "Highway 1416, Box Elder, SD 57719",
    "acres":    "24.75",
    "zoning":   "C-2 (General Commercial)",
    "price":    "$3,750,000",
    "price_per_acre": "$151,515/AC",
    "utilities": "All municipal utilities stubbed to site",
    "frontage":  "Direct Highway 1416 frontage — high-visibility arterial",
    "location_notes": [
        "Box Elder is one of the fastest-growing communities in South Dakota",
        "Adjacent to Ellsworth Air Force Base — 5,000+ personnel, $1.4B annual economic impact",
        "Ellsworth selected for B-21 Raider basing — largest USAF investment in a generation",
        "I-90 interchange proximity — regional distribution and retail access",
        "Pennington County C-2 zoning allows multifamily, commercial, light industrial, mixed-use",
        "No flood zone, no environmental encumbrances",
    ],
}

# ── Target contacts ──────────────────────────────────────────────────────────
TARGETS = [
    {"name": "Lloyd",  "company": "Lloyd Companies",    "email": "ljessen@lloydcompanies.com"},
    {"name": "Lloyd",  "company": "Lloyd Companies",    "email": "admin@lloydcompanies.com"},
    {"name": "Randy",  "company": "Muth Holdings",      "email": "rmuth@muthelectric.com"},
    {"name": "Chris",  "company": "Ernst Capital Group","email": "chris@ernstcapitalgroup.com"},
    {"name": "Scott",  "company": "Vantis Commercial",  "email": "scott@vantiscommercial.com"},
    {"name": "Alex",   "company": "Bender Co.",         "email": "alex@benderco.com"},
]


def generate_email(target: dict) -> dict:
    """Use Claude to write a personalized first-touch email for this target."""
    if not ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY not set — using fallback copy.")
        return _fallback_copy(target)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    location_bullets = "\n".join(f"- {note}" for note in PROPERTY["location_notes"])

    prompt = f"""You are writing a first-touch outreach email on behalf of Kevin Andreson, a commercial real estate agent at Keller Williams Realty Black Hills in Rapid City, SD.

The recipient is {target['name']} at {target['company']}. This is a cold outreach — they have not spoken before. The email must be:
- Sophisticated, direct, and confident — not salesy or generic
- Investor/developer tone, not agent tone — lead with the opportunity, not the listing
- Short: 3 tight paragraphs max
- Specific: use real numbers from the property details
- No clichés ("I hope this email finds you well", "exciting opportunity", "don't miss out")
- End with a low-pressure ask for a 15-minute call

Property being offered:
- Name: {PROPERTY['name']} — {PROPERTY['address']}
- Size: {PROPERTY['acres']} acres, {PROPERTY['zoning']}
- Price: {PROPERTY['price']} ({PROPERTY['price_per_acre']})
- Utilities: {PROPERTY['utilities']}
- Frontage: {PROPERTY['frontage']}
- Location context:
{location_bullets}

Kevin's contact:
- Email: {REPLY_TO}
- Phone: 605-646-5409
- Brokerage: Keller Williams Realty Black Hills

Return a JSON object with exactly these fields:
- subject: the email subject line (compelling, specific, under 60 chars)
- body_html: full HTML email body (no outer HTML/head/body tags — just the content div)
- body_text: plain text version of the same email

Output only valid JSON."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    import json, re
    raw = msg.content[0].text.strip()
    match = re.search(r'\{[\s\S]*\}', raw)
    if match:
        return json.loads(match.group())
    return _fallback_copy(target)


def _fallback_copy(target: dict) -> dict:
    subject = f"24.75-Acre C-2 Site — Box Elder/Ellsworth Corridor"
    body_text = f"""Hi {target['name']},

I'm reaching out about a 24.75-acre C-2 development site on Highway 1416 in Box Elder, SD — positioned directly in the Ellsworth AFB growth corridor.

The site is priced at $3,750,000 ($151,515/AC), fully entitled C-2, with all municipal utilities stubbed to the parcel and direct highway frontage. With Ellsworth's B-21 Raider basing confirmed and Box Elder's continued residential expansion, this is one of the strongest development positions in western South Dakota right now.

Happy to send the full package or get on a 15-minute call if this fits your pipeline. My number is 605-646-5409.

Kevin Andreson
Keller Williams Realty Black Hills
{REPLY_TO}"""
    return {"subject": subject, "body_html": body_text.replace("\n", "<br/>"), "body_text": body_text}


def build_preview_email(emails: list) -> str:
    """Build an HTML preview email showing all drafts for Kevin's review."""
    blocks = ""
    for i, (target, draft) in enumerate(emails, 1):
        blocks += f"""
        <div style="margin-bottom:36px;border:1px solid #E2E8F0;border-radius:12px;overflow:hidden;">
          <div style="background:#0F172A;padding:14px 20px;">
            <div style="font-size:10px;font-weight:700;letter-spacing:0.12em;color:#94A3B8;text-transform:uppercase;margin-bottom:4px;">Draft {i} of {len(emails)} — {target['company']}</div>
            <div style="font-size:13px;color:#fff;font-weight:600;">To: {target['name']} &lt;{target['email']}&gt;</div>
            <div style="font-size:12px;color:#60A5FA;margin-top:4px;">Subject: {draft['subject']}</div>
          </div>
          <div style="padding:20px 24px;background:#fff;font-family:Arial,sans-serif;font-size:13px;line-height:1.75;color:#334155;">
            {draft['body_html']}
          </div>
        </div>"""

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;background:#F8FAFC;padding:24px;">
      <div style="background:#1B3A6B;border-radius:12px;padding:24px 28px;margin-bottom:28px;">
        <div style="font-size:10px;font-weight:700;letter-spacing:0.14em;color:#93C5FD;text-transform:uppercase;margin-bottom:6px;">MDR Campaign Preview</div>
        <div style="font-size:22px;font-weight:900;color:#fff;">Review Before Sending</div>
        <div style="font-size:12px;color:rgba(255,255,255,0.6);margin-top:6px;">{len(emails)} draft emails · {datetime.now().strftime('%B %d, %Y')} · Highway 1416, Box Elder SD</div>
      </div>
      <div style="background:#FEF9C3;border:1px solid #FDE047;border-radius:10px;padding:14px 18px;margin-bottom:28px;font-size:12px;color:#713F12;line-height:1.7;">
        <strong>Action required:</strong> Review each draft below. When ready, send each email manually from arecblackhills@gmail.com.
        Reply to this email with any edits and I'll regenerate.
      </div>
      {blocks}
    </div>"""


def send_preview(html: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"MDR Campaign — {len(TARGETS)} Draft Emails Ready for Review"
    msg["From"]    = FROM_EMAIL
    msg["To"]      = FROM_EMAIL
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(FROM_EMAIL, GMAIL_APP_PASSWORD)
        smtp.sendmail(FROM_EMAIL, FROM_EMAIL, msg.as_string())
    print(f"✓ Preview sent to {FROM_EMAIL}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", action="store_true", help="Print drafts only, no email")
    args = ap.parse_args()

    print("\nMDR Land Marketing Campaign")
    print("=" * 44)
    print(f"Property: {PROPERTY['address']} · {PROPERTY['acres']} AC · {PROPERTY['price']}")
    print(f"Targets:  {len(TARGETS)} contacts\n")

    emails = []
    for target in TARGETS:
        print(f"  Drafting email for {target['name']} at {target['company']}...")
        draft = generate_email(target)
        emails.append((target, draft))
        print(f"  ✓ Subject: {draft['subject']}")

    if args.draft:
        print("\n── Drafts ──────────────────────────────────────────")
        for target, draft in emails:
            print(f"\nTO: {target['name']} <{target['email']}>")
            print(f"SUBJECT: {draft['subject']}")
            print(draft["body_text"])
            print("─" * 52)
        return

    print(f"\nSending preview to {FROM_EMAIL}...")
    html = build_preview_email(emails)
    send_preview(html)
    print("\nDone. Check your inbox — review the drafts and send manually when ready.\n")


if __name__ == "__main__":
    main()
