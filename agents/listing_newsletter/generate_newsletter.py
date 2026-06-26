#!/usr/bin/env python3
"""
Monthly Listing Newsletter Agent — Kevin Andreson / Keller Williams Black Hills
Generates photo-card email with AI copy for each featured property.

Usage — one --listing flag per property, pipe-delimited fields:
  python3 generate_newsletter.py \
    --listing "Highway 1416 Box Elder SD | $3,750,000 | 24.75 AC · C-2 · Hwy Frontage | https://photo.jpg" \
    --listing "456 Main St Rapid City SD | $1,200,000 | 8.5 AC · C-1" \
    --message "Strong Q3 demand across the corridor." \
    --dry-run

Fields per --listing (all but name are optional):
  Name/Address | Price | Specs (size · zoning · highlights) | Photo URL

Quick mode (no photos, just addresses):
  python3 generate_newsletter.py --properties "Hwy 1416 Box Elder, 456 Main Rapid City" --dry-run
"""
import argparse, json, os, re, smtplib, sys, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hwy1416_newsletter'))
from config import FROM_EMAIL, REPLY_TO, GMAIL_APP_PASSWORD, RECIPIENTS

try:
    import anthropic
    AI_ENABLED = True
except ImportError:
    AI_ENABLED = False

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def parse_listing(raw: str) -> dict:
    """Parse a pipe-delimited listing string into a dict."""
    parts = [p.strip() for p in raw.split("|")]
    return {
        "name":    parts[0] if len(parts) > 0 else "",
        "price":   parts[1] if len(parts) > 1 else "",
        "specs":   parts[2] if len(parts) > 2 else "",
        "photo":   parts[3] if len(parts) > 3 else "",
    }


def generate_copy(listings: list[dict], extra_message: str) -> list[dict]:
    """Call Claude to write headline + copy + CTA for each listing."""
    if not AI_ENABLED or not ANTHROPIC_API_KEY:
        print("  [info] ANTHROPIC_API_KEY not set — using plain property info. Set it to enable AI copy.")
        for l in listings:
            l.setdefault("headline", l["name"].upper())
            l.setdefault("copy", f"{l['name']} — {l.get('specs', '')}. Contact Kevin for details.")
            l.setdefault("cta", "Contact Kevin Andreson for more information.")
        return listings

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    for l in listings:
        prop_detail = l["name"]
        if l.get("price"):  prop_detail += f", asking {l['price']}"
        if l.get("specs"):  prop_detail += f", {l['specs']}"

        prompt = f"""You are a commercial real estate marketing copywriter for Kevin Andreson at Keller Williams Realty Black Hills, Rapid City SD.

Write compelling email newsletter copy for this listing. Recipients are apartment developers, commercial investors, and operators in the Black Hills/Ellsworth AFB corridor.

Property: {prop_detail}
Agent context: {extra_message or 'No additional context.'}

Return ONLY a JSON object with these exact fields:
- headline: 6-10 word headline in ALL CAPS, investment-focused
- copy: 2-3 sentences. Lead with the strongest investment angle. Specific numbers if available.
- cta: one punchy sentence encouraging them to reach out

Output only valid JSON."""

        try:
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = msg.content[0].text.strip()
            data = json.loads(re.search(r'\{.*\}', raw, re.DOTALL).group())
            l["headline"] = data.get("headline", l["name"].upper())
            l["copy"]     = data.get("copy", "")
            l["cta"]      = data.get("cta", "Contact Kevin Andreson for more information.")
        except Exception as e:
            print(f"  [warn] Claude failed for '{l['name']}': {e}")
            l["headline"] = l["name"].upper()
            l["copy"]     = f"{l['name']}. Contact Kevin for full details."
            l["cta"]      = "Contact Kevin Andreson for more information."
        print(f"  ✓ Copy generated for: {l['name']}")

    return listings


def _spec_badges(specs: str) -> str:
    """Turn 'X · Y · Z' into inline badge chips."""
    if not specs:
        return ""
    parts = [s.strip() for s in re.split(r'[·|,]', specs) if s.strip()]
    chips = "".join(
        f'<span style="display:inline-block;background:#EFF6FF;border:1px solid #BFDBFE;'
        f'color:#1E40AF;font-size:10px;font-weight:700;padding:3px 10px;border-radius:20px;'
        f'margin:0 5px 5px 0;letter-spacing:0.04em;text-transform:uppercase;">{p}</span>'
        for p in parts
    )
    return f'<div style="margin:0 0 14px 0;">{chips}</div>'


def _photo_block(photo_url: str) -> str:
    if not photo_url:
        return ""
    return (
        f'<tr><td style="padding:0;">'
        f'<img src="{photo_url}" width="620" '
        f'style="display:block;width:100%;max-height:320px;object-fit:cover;" alt=""/>'
        f'</td></tr>'
    )


def _price_badge(price: str) -> str:
    if not price:
        return ""
    return (
        f'<span style="display:inline-block;background:#1B3A6B;color:#fff;'
        f'font-size:18px;font-weight:900;padding:6px 16px;border-radius:6px;'
        f'letter-spacing:0.02em;margin-bottom:10px;">{price}</span>'
    )


def build_html(listings: list[dict], extra_message: str) -> str:
    month = datetime.now().strftime("%B %Y")
    intro = (
        f'<tr><td style="padding:0 28px 20px;">'
        f'<p style="margin:0;font-size:14px;line-height:1.75;color:#475569;">{extra_message}</p>'
        f'</td></tr>'
    ) if extra_message else ""

    listing_blocks = ""
    for l in listings:
        photo   = _photo_block(l.get("photo", ""))
        price   = _price_badge(l.get("price", ""))
        badges  = _spec_badges(l.get("specs", ""))
        headline = l.get("headline", l["name"].upper())
        copy     = l.get("copy", "")
        cta      = l.get("cta", "Contact Kevin Andreson for more information.")
        name     = l["name"]

        listing_blocks += f"""
  <!-- Listing: {name} -->
  <tr><td style="padding:0 0 28px 0;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="border:1px solid #E2E8F0;border-radius:10px;overflow:hidden;background:#fff;">
      {photo}
      <tr><td style="background:#0F172A;padding:16px 22px;">
        <p style="margin:0;font-size:11px;font-weight:700;letter-spacing:0.14em;
           text-transform:uppercase;color:#60A5FA;">{name}</p>
        <p style="margin:6px 0 0;font-size:15px;font-weight:900;color:#fff;
           letter-spacing:0.04em;text-transform:uppercase;line-height:1.2;">{headline}</p>
      </td></tr>
      <tr><td style="padding:18px 22px 20px;">
        {price}
        {badges}
        <p style="margin:0 0 16px;font-size:13px;line-height:1.75;color:#334155;">{copy}</p>
        <a href="mailto:arecblackhills@gmail.com?subject=Inquiry — {name}"
           style="display:inline-block;background:#1B3A6B;color:#fff;font-size:12px;
           font-weight:700;letter-spacing:0.06em;text-decoration:none;padding:10px 22px;
           border-radius:5px;">{cta}</a>
      </td></tr>
    </table>
  </td></tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head>
<body style="margin:0;padding:0;background:#F1F5F9;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F1F5F9;">
<tr><td align="center" style="padding:24px 12px;">
<table width="620" cellpadding="0" cellspacing="0" border="0"
       style="max-width:620px;background:#fff;border-radius:12px;overflow:hidden;
              box-shadow:0 4px 24px rgba(0,0,0,0.08);">

  <!-- Header -->
  <tr><td style="background:#0F172A;padding:18px 28px;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td style="font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;
                 color:#94A3B8;">KELLER WILLIAMS REALTY BLACK HILLS</td>
      <td align="right" style="font-size:11px;color:#475569;letter-spacing:0.04em;">Kevin Andreson</td>
    </tr></table>
  </td></tr>

  <!-- Title band -->
  <tr><td style="background:#1B3A6B;padding:22px 28px 18px;">
    <p style="margin:0 0 4px;font-size:10px;font-weight:700;letter-spacing:0.16em;
       text-transform:uppercase;color:#93C5FD;">{month} Featured Listings</p>
    <p style="margin:0;font-size:22px;font-weight:900;color:#fff;line-height:1.2;">
      Black Hills Commercial Properties</p>
    <p style="margin:6px 0 0;font-size:12px;color:rgba(255,255,255,0.55);">
      Rapid City · Box Elder · Black Hills Region, South Dakota</p>
  </td></tr>

  {intro}

  <!-- Listings -->
  <tr><td style="padding:24px 24px 8px;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0">
      {listing_blocks}
    </table>
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#0F172A;padding:18px 28px;border-top:1px solid #1E293B;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td>
        <p style="margin:0;font-size:13px;font-weight:700;color:#fff;">Kevin Andreson</p>
        <p style="margin:3px 0 0;font-size:11px;color:#64748B;">
          Keller Williams Realty Black Hills &nbsp;·&nbsp;
          <a href="mailto:arecblackhills@gmail.com" style="color:#60A5FA;text-decoration:none;">
            arecblackhills@gmail.com</a> &nbsp;·&nbsp; 605-646-5409</p>
      </td>
      <td align="right">
        <p style="margin:0;font-size:10px;color:#475569;">KWBLACKHILLS.COM</p>
      </td>
    </tr></table>
    <p style="margin:14px 0 0;font-size:9px;color:#475569;line-height:1.6;">
      You are receiving this as part of our commercial real estate investor network.
      Reply with "unsubscribe" to be removed.
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""


def send(subject: str, html: str, dry_run: bool = False, send_all: bool = False):
    if dry_run:
        out = "preview_listing_newsletter.html"
        with open(out, "w") as f:
            f.write(html)
        print(f"\nDRY RUN — Subject: {subject}")
        print(f"Preview saved → {out}  (open in browser to review)")
        return

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(FROM_EMAIL, GMAIL_APP_PASSWORD)

        print(f"\n── Preview send to {REPLY_TO} ──────────────────")
        msg = MIMEMultipart("alternative")
        msg["Subject"]  = f"[PREVIEW] {subject}"
        msg["From"]     = f"Kevin Andreson | Keller Williams Black Hills <{FROM_EMAIL}>"
        msg["To"]       = REPLY_TO
        msg["Reply-To"] = REPLY_TO
        msg.attach(MIMEText(html, "html"))
        smtp.sendmail(FROM_EMAIL, REPLY_TO, msg.as_string())
        print(f"  ✓ {REPLY_TO}")

        if not send_all:
            print(f"\nPreview sent. Review in Gmail, then rerun with --send-all to deliver to all {len(RECIPIENTS)} recipients.")
            return

        print(f"\n── Full send ({len(RECIPIENTS)} recipients) ──────────────")
        sent, failed = 0, []
        for to in RECIPIENTS:
            try:
                m = MIMEMultipart("alternative")
                m["Subject"]  = subject
                m["From"]     = f"Kevin Andreson | Keller Williams Black Hills <{FROM_EMAIL}>"
                m["To"]       = to
                m["Reply-To"] = REPLY_TO
                m.attach(MIMEText(html, "html"))
                smtp.sendmail(FROM_EMAIL, to, m.as_string())
                sent += 1
                print(f"  ✓ {to}")
                time.sleep(0.3)
            except Exception as e:
                failed.append((to, str(e)))
                print(f"  ✗ {to}: {e}")

        print(f"\nSent: {sent}/{len(RECIPIENTS)}")
        if failed:
            for addr, err in failed:
                print(f"  FAILED: {addr}: {err}")


def main():
    parser = argparse.ArgumentParser(
        description="Monthly listing newsletter — AI copy + photo cards per property."
    )
    parser.add_argument(
        "--listing", action="append", dest="listings", metavar="LISTING",
        help=(
            'Pipe-delimited property: "Name | Price | Specs | PhotoURL"  '
            '(repeat flag for multiple properties)'
        )
    )
    parser.add_argument(
        "--properties",
        help='Quick mode: comma-separated addresses with no photos (e.g. "Addr1, Addr2")'
    )
    parser.add_argument("--message",  default="", help="Optional intro paragraph for the email")
    parser.add_argument("--subject",  default=None, help="Override email subject line")
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--send-all", action="store_true")
    args = parser.parse_args()

    raw_listings = []

    if args.listings:
        raw_listings = [parse_listing(l) for l in args.listings]
    elif args.properties:
        raw_listings = [{"name": p.strip(), "price": "", "specs": "", "photo": ""}
                        for p in args.properties.split(",") if p.strip()]
    else:
        parser.error("Provide at least one --listing or --properties argument.")

    print(f"\nMonthly Listing Newsletter — {len(raw_listings)} propert{'y' if len(raw_listings)==1 else 'ies'}")
    print("=" * 48)
    print("Generating AI copy...")
    listings = generate_copy(raw_listings, args.message)

    month   = datetime.now().strftime("%B %Y")
    subject = args.subject or f"Black Hills Commercial Listings — {month}"
    html    = build_html(listings, args.message)

    send(subject, html, dry_run=args.dry_run, send_all=args.send_all)


if __name__ == "__main__":
    main()
