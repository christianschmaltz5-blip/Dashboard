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
PREVIEW_TO = REPLY_TO  # arecblackhills@gmail.com

# ── Conceptual site plan SVG (inline for email embedding) ────────────────────
SITE_PLAN_SVG = """
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:28px 0;">
  <tr><td>
    <p style="margin:0 0 10px;font-size:9px;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;color:#64748B;font-family:Arial,sans-serif;">Conceptual Site Plan</p>
    <div style="border:1px solid #E2E8F0;border-radius:8px;overflow:hidden;background:#F5EFE4;">
      <svg viewBox="0 0 680 340" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;display:block;">
        <rect width="680" height="340" fill="#F5EFE4"/>
        <polygon points="62,42 622,36 638,190 556,320 118,318 44,210" fill="#EDE6D5" stroke="#C0B89A" stroke-width="1.5"/>
        <path d="M 198,112 Q 295,104 340,112 Q 390,120 482,112 L 482,130 Q 388,138 340,132 Q 290,126 198,134 Z" fill="#8FBC70" opacity="0.55"/>
        <ellipse cx="172" cy="218" rx="60" ry="42" fill="#8FBC70" opacity="0.42"/>
        <ellipse cx="490" cy="218" rx="56" ry="40" fill="#8FBC70" opacity="0.42"/>
        <path d="M 108,262 Q 220,248 340,254 Q 462,258 556,262 Q 558,305 540,315 Q 420,326 340,327 Q 222,328 138,318 Q 100,312 108,262 Z" fill="#8FBC70" opacity="0.45"/>
        <ellipse cx="172" cy="212" rx="19" ry="13" fill="#5BC4C0" opacity="0.72"/>
        <ellipse cx="172" cy="212" rx="14" ry="9" fill="#3AB8B4" opacity="0.55"/>
        <ellipse cx="492" cy="212" rx="18" ry="13" fill="#5BC4C0" opacity="0.72"/>
        <ellipse cx="492" cy="212" rx="13" ry="9" fill="#3AB8B4" opacity="0.55"/>
        <ellipse cx="340" cy="194" rx="34" ry="20" fill="#5BC4C0" opacity="0.65"/>
        <ellipse cx="340" cy="194" rx="26" ry="14" fill="#3AB8B4" opacity="0.48"/>
        <path d="M 230,295 Q 285,283 340,286 Q 395,283 445,295 Q 452,312 428,318 Q 380,324 340,326 Q 300,324 254,318 Q 222,312 230,295 Z" fill="#5BC4C0" opacity="0.35"/>
        <rect x="0" y="12" width="680" height="22" fill="#C2BAA8"/>
        <line x1="0" y1="23" x2="680" y2="23" stroke="#A89E8C" stroke-width="1" stroke-dasharray="16,8"/>
        <rect x="220" y="34" width="18" height="100" fill="#D0C8B5" rx="1"/>
        <path d="M 116,138 Q 90,160 86,196 Q 84,232 106,256 Q 134,278 172,280 Q 212,280 236,262 Q 256,246 258,224 Q 260,200 244,182 Q 226,164 206,158 Q 186,152 168,156 Q 144,162 128,178 Q 114,195 114,212" stroke="#D0C8B5" stroke-width="12" fill="none" stroke-linecap="round"/>
        <path d="M 462,138 Q 490,142 518,160 Q 548,182 550,214 Q 552,250 530,272 Q 506,292 474,292 Q 442,292 418,274 Q 396,258 394,234 Q 392,208 408,190 Q 426,170 448,162 Q 466,154 484,158" stroke="#D0C8B5" stroke-width="12" fill="none" stroke-linecap="round"/>
        <rect x="255" y="206" width="128" height="16" fill="#D0C8B5" rx="1"/>
        <rect x="72" y="44" width="70" height="38" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="2"/>
        <rect x="72" y="44" width="70" height="3" fill="#C0B89A"/>
        <rect x="155" y="43" width="56" height="37" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="2"/>
        <rect x="155" y="43" width="56" height="3" fill="#C0B89A"/>
        <rect x="252" y="42" width="70" height="37" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="2"/>
        <rect x="252" y="42" width="70" height="3" fill="#C0B89A"/>
        <rect x="336" y="42" width="56" height="37" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="2"/>
        <rect x="336" y="42" width="56" height="3" fill="#C0B89A"/>
        <rect x="405" y="41" width="70" height="37" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="2"/>
        <rect x="405" y="41" width="70" height="3" fill="#C0B89A"/>
        <rect x="490" y="41" width="68" height="37" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="2"/>
        <rect x="490" y="41" width="68" height="3" fill="#C0B89A"/>
        <rect x="572" y="41" width="52" height="37" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="2"/>
        <rect x="572" y="41" width="52" height="3" fill="#C0B89A"/>
        <rect x="100" y="152" width="46" height="30" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="1"/>
        <rect x="155" y="146" width="46" height="30" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="1"/>
        <rect x="94" y="190" width="44" height="28" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="1"/>
        <rect x="148" y="196" width="44" height="28" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="1"/>
        <rect x="96" y="232" width="44" height="28" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="1"/>
        <rect x="148" y="236" width="44" height="28" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="1"/>
        <rect x="462" y="148" width="48" height="30" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="1"/>
        <rect x="520" y="154" width="46" height="30" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="1"/>
        <rect x="460" y="186" width="50" height="28" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="1"/>
        <rect x="518" y="192" width="48" height="28" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="1"/>
        <rect x="462" y="228" width="48" height="28" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="1"/>
        <rect x="518" y="228" width="48" height="28" fill="#FAFAF2" stroke="#C8C0AE" stroke-width="1" rx="1"/>
        <rect x="296" y="150" width="88" height="40" fill="#F5EDE0" stroke="#C8C0AE" stroke-width="1" rx="3"/>
        <circle cx="68" cy="37" r="4" fill="#5A8040" opacity="0.65"/>
        <circle cx="156" cy="36" r="4" fill="#6A9048" opacity="0.6"/>
        <circle cx="246" cy="36" r="4" fill="#5A8040" opacity="0.65"/>
        <circle cx="330" cy="36" r="4" fill="#6A9048" opacity="0.6"/>
        <circle cx="400" cy="36" r="4" fill="#5A8040" opacity="0.65"/>
        <circle cx="488" cy="36" r="4" fill="#6A9048" opacity="0.6"/>
        <circle cx="568" cy="36" r="4" fill="#5A8040" opacity="0.65"/>
        <circle cx="630" cy="36" r="4" fill="#6A9048" opacity="0.6"/>
        <circle cx="50" cy="92" r="5" fill="#5A8040" opacity="0.55"/>
        <circle cx="48" cy="185" r="5" fill="#5A8040" opacity="0.55"/>
        <circle cx="64" cy="278" r="5" fill="#5A8040" opacity="0.55"/>
        <circle cx="120" cy="305" r="5" fill="#5A8040" opacity="0.55"/>
        <circle cx="390" cy="312" r="5" fill="#5A8040" opacity="0.55"/>
        <circle cx="554" cy="302" r="5" fill="#5A8040" opacity="0.55"/>
        <circle cx="632" cy="238" r="5" fill="#5A8040" opacity="0.55"/>
        <circle cx="638" cy="160" r="4" fill="#5A8040" opacity="0.55"/>
        <text x="340" y="25" text-anchor="middle" font-family="Arial,sans-serif" font-size="7" font-weight="700" letter-spacing="2" fill="#5C5040">HIGHWAY 1416 FRONTAGE</text>
        <text x="340" y="56" text-anchor="middle" font-family="Arial,sans-serif" font-size="6" font-weight="700" letter-spacing="1.5" fill="#7A7060">COMMERCIAL PAD SITES — C-2</text>
        <text x="152" y="134" text-anchor="middle" font-family="Arial,sans-serif" font-size="6" font-weight="700" letter-spacing="1" fill="#7A7060">PHASE 1</text>
        <text x="152" y="143" text-anchor="middle" font-family="Arial,sans-serif" font-size="5.5" fill="#9A9080">MULTIFAMILY</text>
        <text x="490" y="134" text-anchor="middle" font-family="Arial,sans-serif" font-size="6" font-weight="700" letter-spacing="1" fill="#7A7060">PHASE 2</text>
        <text x="490" y="143" text-anchor="middle" font-family="Arial,sans-serif" font-size="5.5" fill="#9A9080">MULTIFAMILY</text>
        <text x="340" y="162" text-anchor="middle" font-family="Arial,sans-serif" font-size="6" font-weight="700" letter-spacing="1" fill="#7A7060">AMENITY COURT</text>
        <text x="340" y="290" text-anchor="middle" font-family="Arial,sans-serif" font-size="5.5" fill="#9A9080" letter-spacing="1">OPEN SPACE / STORMWATER</text>
        <rect x="500" y="326" width="90" height="3" fill="#9A9080"/>
        <rect x="500" y="324" width="1" height="7" fill="#9A9080"/>
        <rect x="545" y="324" width="1" height="7" fill="#9A9080"/>
        <rect x="590" y="324" width="1" height="7" fill="#9A9080"/>
        <text x="498" y="336" font-family="Arial,sans-serif" font-size="5.5" fill="#9A9080">0</text>
        <text x="535" y="336" font-family="Arial,sans-serif" font-size="5.5" fill="#9A9080">250 FT</text>
        <text x="582" y="336" font-family="Arial,sans-serif" font-size="5.5" fill="#9A9080">500 FT</text>
        <g transform="translate(46,325)">
          <polygon points="0,-12 4,0 0,-3 -4,0" fill="#8C7860"/>
          <polygon points="0,-3 4,0 0,7 -4,0" fill="#C0B89A"/>
          <text x="0" y="17" text-anchor="middle" font-family="Arial,sans-serif" font-size="7" font-weight="700" fill="#7A7060">N</text>
        </g>
        <text x="340" y="336" text-anchor="middle" font-family="Arial,sans-serif" font-size="6.5" font-weight="700" fill="#8C7860" letter-spacing="1">24.75 AC · BOX ELDER, SD · ALL UTILITIES AVAILABLE</text>
      </svg>
    </div>
    <p style="margin:6px 0 0;font-size:9px;color:#94A3B8;font-family:Arial,sans-serif;font-style:italic;">Conceptual site plan — not to scale. Subject to final design, engineering &amp; regulatory approval.</p>
  </td></tr>
</table>
"""

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
            {SITE_PLAN_SVG}
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
    msg["To"]      = PREVIEW_TO
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(FROM_EMAIL, GMAIL_APP_PASSWORD)
        smtp.sendmail(FROM_EMAIL, PREVIEW_TO, msg.as_string())
    print(f"✓ Preview sent to {PREVIEW_TO}")


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

    print(f"\nSending preview to {PREVIEW_TO}...")
    html = build_preview_email(emails)
    send_preview(html)
    print("\nDone. Check your inbox — review the drafts and send manually when ready.\n")


if __name__ == "__main__":
    main()
