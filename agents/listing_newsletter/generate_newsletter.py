#!/usr/bin/env python3
"""
Monthly Listing Newsletter Agent
Usage:
  python3 generate_newsletter.py \
    --properties "123 Main St Rapid City SD, 456 Elm Ave Box Elder SD" \
    --message "Strong buyer demand heading into Q3" \
    --dry-run

  python3 generate_newsletter.py \
    --properties "123 Main St, 456 Elm Ave" \
    --send-all
"""
import argparse, os, smtplib, sys, time, io
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


def generate_listing_copy(properties: list[str], extra_message: str) -> list[dict]:
    """Use Claude to write marketing copy for each property."""
    if not AI_ENABLED or not ANTHROPIC_API_KEY:
        # Fallback: use plain property info
        return [{"address": p, "headline": p, "copy": p, "cta": "Contact us for details."} for p in properties]

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    results = []
    for prop in properties:
        prompt = f"""You are a commercial real estate marketing copywriter for Kevin Andreson at Keller Williams Realty Black Hills in Rapid City, SD.

Write a short, professional marketing blurb for this listing to include in a monthly email newsletter sent to apartment developers, investors, and commercial operators in the Black Hills region.

Property: {prop}
Agent note: {extra_message or 'No additional context.'}

Return a JSON object with exactly these fields:
- headline: punchy 6-10 word headline (ALL CAPS)
- copy: 2-3 sentence property description, professional and compelling, focused on investment opportunity
- cta: one short call-to-action sentence

Output ONLY valid JSON, no other text."""

        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        import json, re
        raw = msg.content[0].text.strip()
        try:
            data = json.loads(re.search(r'\{.*\}', raw, re.DOTALL).group())
        except Exception:
            data = {"headline": prop.upper(), "copy": prop, "cta": "Contact us for details."}
        data["address"] = prop
        results.append(data)

    return results


def build_html(listings: list[dict], extra_message: str) -> str:
    month = datetime.now().strftime("%B %Y")
    listing_blocks = ""

    for i, l in enumerate(listings):
        bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
        listing_blocks += f"""
    <tr><td style="padding:0 0 24px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:{bg};border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
        <tr>
          <td style="background:#1B3A6B;padding:14px 20px;">
            <p style="margin:0;font-size:13px;font-weight:bold;color:#fff;letter-spacing:0.06em;text-transform:uppercase;">{l.get('headline','FEATURED LISTING')}</p>
            <p style="margin:4px 0 0 0;font-size:11px;color:rgba(255,255,255,0.6);letter-spacing:0.04em;">{l.get('address','')}</p>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 20px;">
            <p style="margin:0 0 12px 0;font-size:13px;line-height:1.7;color:#334155;">{l.get('copy','')}</p>
            <p style="margin:0;font-size:12px;font-weight:bold;color:#1B3A6B;">{l.get('cta','')}</p>
          </td>
        </tr>
      </table>
    </td></tr>"""

    intro = f'<p style="margin:0 0 16px 0;font-size:14px;line-height:1.7;color:#334155;">{extra_message}</p>' if extra_message else ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f1f5f9;">
<tr><td align="center" style="padding:24px 12px;">
<table width="620" cellpadding="0" cellspacing="0" border="0"
       style="max-width:620px;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

  <!-- Header -->
  <tr><td style="background:#0f172a;padding:20px 28px;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td style="font-size:11px;font-weight:bold;letter-spacing:0.12em;text-transform:uppercase;color:#94a3b8;">KELLER WILLIAMS REALTY BLACK HILLS</td>
      <td align="right" style="font-size:11px;color:#475569;letter-spacing:0.04em;">Keller Williams Black Hills</td>
    </tr></table>
  </td></tr>

  <!-- Title band -->
  <tr><td style="background:#1B3A6B;padding:22px 28px 18px;">
    <p style="margin:0 0 4px 0;font-size:10px;font-weight:bold;letter-spacing:0.16em;text-transform:uppercase;color:#93C5FD;">{month} Featured Listings</p>
    <p style="margin:0;font-size:22px;font-weight:bold;color:#fff;line-height:1.2;">Black Hills Commercial Properties</p>
    <p style="margin:6px 0 0 0;font-size:12px;color:rgba(255,255,255,0.6);">Rapid City · Box Elder · Black Hills Region</p>
  </td></tr>

  <!-- Body -->
  <tr><td style="padding:24px 28px 8px;">
    {intro}
    <table width="100%" cellpadding="0" cellspacing="0" border="0">
      {listing_blocks}
    </table>
  </td></tr>

  <!-- CTA -->
  <tr><td align="center" style="padding:8px 28px 28px;">
    <a href="mailto:arecblackhills@gmail.com?subject=Property Inquiry — {month}"
       style="display:inline-block;background:#1B3A6B;color:#fff;font-size:13px;font-weight:bold;letter-spacing:0.06em;text-decoration:none;padding:13px 32px;border-radius:6px;">
      Schedule a Showing
    </a>
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#0f172a;padding:18px 28px;border-top:1px solid #1e293b;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td><p style="margin:0;font-size:12px;font-weight:bold;color:#fff;">Kevin Andreson</p>
          <p style="margin:3px 0 0;font-size:11px;color:#64748b;">Keller Williams Realty Black Hills &nbsp;·&nbsp;
          <a href="mailto:arecblackhills@gmail.com" style="color:#60a5fa;text-decoration:none;">arecblackhills@gmail.com</a> &nbsp;·&nbsp; 605-646-5409</p></td>
      <td align="right"><p style="margin:0;font-size:10px;color:#475569;">KWBLACKHILLS.COM</p></td>
    </tr></table>
    <p style="margin:14px 0 0;font-size:9px;color:#334155;line-height:1.6;">
      You are receiving this as part of our commercial real estate investor network.
      To unsubscribe, reply with "unsubscribe" in the subject line.
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""


def send(subject: str, html: str, dry_run: bool = False, send_all: bool = False):
    if dry_run:
        print(f"\nDRY RUN — Subject: {subject}")
        with open("preview_listing_newsletter.html", "w") as f:
            f.write(html)
        print("Preview saved: preview_listing_newsletter.html")
        return

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(FROM_EMAIL, GMAIL_APP_PASSWORD)

        # Always send preview to Kevin first
        print(f"\n── Preview send ──────────────────")
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[PREVIEW] {subject}"
        msg["From"]    = f"Kevin Andreson | Keller Williams Black Hills <{FROM_EMAIL}>"
        msg["To"]      = REPLY_TO
        msg["Reply-To"] = REPLY_TO
        msg.attach(MIMEText(html, "html"))
        smtp.sendmail(FROM_EMAIL, REPLY_TO, msg.as_string())
        print(f"  ✓ {REPLY_TO}")

        if not send_all:
            print(f"\nPreview sent. Review at {REPLY_TO}, then rerun with --send-all.")
            return

        print(f"\n── Full send ({len(RECIPIENTS)} recipients) ──")
        sent, failed = 0, []
        for to in RECIPIENTS:
            try:
                m = MIMEMultipart("alternative")
                m["Subject"] = subject
                m["From"]    = f"Kevin Andreson — AREC Black Hills <{FROM_EMAIL}>"
                m["To"]      = to
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--properties", required=True,
                        help='Comma-separated property addresses, e.g. "123 Main St, 456 Elm Ave"')
    parser.add_argument("--message",  default="",
                        help="Optional intro paragraph for the email body")
    parser.add_argument("--subject",  default=None,
                        help="Override email subject line")
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--send-all", action="store_true")
    args = parser.parse_args()

    props = [p.strip() for p in args.properties.split(",") if p.strip()]
    print(f"Generating copy for {len(props)} properties...")
    listings = generate_listing_copy(props, args.message)

    month = datetime.now().strftime("%B %Y")
    subject = args.subject or f"Black Hills Commercial Listings — {month}"

    html = build_html(listings, args.message)
    send(subject, html, dry_run=args.dry_run, send_all=args.send_all)


if __name__ == "__main__":
    main()
