#!/usr/bin/env python3
"""
Highway 1416, Box Elder — Newsletter Send Script
Usage:
  python3 send_newsletter.py                          # sends with default content
  python3 send_newsletter.py --subject "Custom Title" --message "Update text here"
  python3 send_newsletter.py --dry-run                # prints email without sending
"""
import argparse
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

from config import FROM_EMAIL, REPLY_TO, GMAIL_APP_PASSWORD, RECIPIENTS, SUBJECT_PREFIX

# ── Property constants ────────────────────────────────────────────────────────
LOOPNET_URL = "https://www.loopnet.com/listing/highway-1416-box-elder-sd/"

PHOTOS = [
    "https://images1.loopnet.com/i2/QGILchjqaRVCkLbafYze9QdMfuROFsVnu1AQ616h_KE/116/Highway-1416-Box-Elder-SD-Primary-Photo-1-LargeHighDefinition.png",
    "https://images1.loopnet.com/i2/28Vs7Jzi7XQFFHQ3sn6WydrFK3Pf0B8NEp338LX3Rsc/116/Highway-1416-Box-Elder-SD-Building-Photo-2-LargeHighDefinition.png",
    "https://images1.loopnet.com/i2/BkWayRvOg1L2SC1nvGsVXPmHFzbD9_qdHCWfa4fiquM/116/Highway-1416-Box-Elder-SD-Building-Photo-3-LargeHighDefinition.jpg",
    "https://images1.loopnet.com/i2/WO6DjGRPB0XgVIxIE82FbIVhHY_OnpSc7Q2tg3FpZ0M/116/Highway-1416-Box-Elder-SD-Building-Photo-4-LargeHighDefinition.jpg",
    "https://images1.loopnet.com/i2/KjFxxHAYpIOiUpkXKKhLNfhzhHw3qIziueht35_Fh2U/116/Highway-1416-Box-Elder-SD-Building-Photo-5-LargeHighDefinition.jpg",
    "https://images1.loopnet.com/i2/mMaKnCff4F3QSIofyudastA7AdLVFHTIn2ftqOOjYnk/116/Highway-1416-Box-Elder-SD-Building-Photo-6-LargeHighDefinition.png",
]

DEFAULT_MESSAGE = """
This prime 24.75-acre commercial parcel on Highway 1416 in Box Elder, SD offers
exceptional visibility and access along one of the Black Hills' fastest-growing corridors.
Zoned commercial with direct highway frontage, this site is ideal for retail, hospitality,
mixed-use development, or a build-to-suit opportunity.

Box Elder continues to attract major investment — with Ellsworth Air Force Base expansion,
rapid residential growth, and strong regional demand, this location positions your project
for long-term appreciation and strong returns.
""".strip()


def build_html(message: str) -> str:
    month = datetime.now().strftime("%B %Y")
    photo_grid = ""
    grid_photos = PHOTOS[1:]  # hero is photo[0], rest go in grid
    for i in range(0, len(grid_photos), 2):
        left = grid_photos[i]
        right = grid_photos[i + 1] if i + 1 < len(grid_photos) else None
        right_td = f'<td width="50%" style="padding:4px 0 0 4px;"><img src="{right}" width="100%" style="display:block;border-radius:4px;" alt=""/></td>' if right else '<td width="50%"></td>'
        photo_grid += f"""
        <tr>
          <td width="50%" style="padding:4px 4px 0 0;"><img src="{left}" width="100%" style="display:block;border-radius:4px;" alt=""/></td>
          {right_td}
        </tr>"""

    # Format message paragraphs
    paras = [p.strip() for p in message.strip().split("\n\n") if p.strip()]
    body_html = "".join(f'<p style="margin:0 0 16px 0;font-size:15px;line-height:1.7;color:#334155;">{p}</p>' for p in paras)

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f1f5f9;">
<tr><td align="center" style="padding:24px 12px;">

  <!-- Outer card -->
  <table width="640" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

    <!-- Top bar -->
    <tr>
      <td style="background:#0f172a;padding:14px 28px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="font-size:11px;font-weight:bold;letter-spacing:0.12em;text-transform:uppercase;color:#94a3b8;">ARECBLACKHILLS.COM</td>
            <td align="right" style="font-size:11px;letter-spacing:0.06em;text-transform:uppercase;color:#475569;">Keller Williams Realty Black Hills</td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Hero image -->
    <tr>
      <td style="padding:0;position:relative;">
        <img src="{PHOTOS[0]}" width="640" style="display:block;width:100%;max-height:340px;object-fit:cover;" alt="Highway 1416, Box Elder SD"/>
      </td>
    </tr>

    <!-- Title band -->
    <tr>
      <td style="background:#0f172a;padding:22px 28px 20px;">
        <p style="margin:0 0 4px 0;font-size:11px;font-weight:bold;letter-spacing:0.14em;text-transform:uppercase;color:#60a5fa;">{month} Update</p>
        <p style="margin:0;font-size:24px;font-weight:bold;color:#ffffff;line-height:1.2;">Highway 1416, Box Elder</p>
        <p style="margin:6px 0 0 0;font-size:14px;color:#94a3b8;">Box Elder, SD 57719 &nbsp;·&nbsp; Commercial Land</p>
      </td>
    </tr>

    <!-- Stats bar -->
    <tr>
      <td style="background:#1e293b;padding:0;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td width="25%" align="center" style="padding:16px 8px;border-right:1px solid #334155;">
              <p style="margin:0;font-size:20px;font-weight:bold;color:#ffffff;">24.75</p>
              <p style="margin:4px 0 0 0;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:#64748b;">Acres</p>
            </td>
            <td width="25%" align="center" style="padding:16px 8px;border-right:1px solid #334155;">
              <p style="margin:0;font-size:20px;font-weight:bold;color:#ffffff;">$3.75M</p>
              <p style="margin:4px 0 0 0;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:#64748b;">Asking Price</p>
            </td>
            <td width="25%" align="center" style="padding:16px 8px;border-right:1px solid #334155;">
              <p style="margin:0;font-size:20px;font-weight:bold;color:#ffffff;">Hwy</p>
              <p style="margin:4px 0 0 0;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:#64748b;">Frontage</p>
            </td>
            <td width="25%" align="center" style="padding:16px 8px;">
              <p style="margin:0;font-size:20px;font-weight:bold;color:#ffffff;">C-2</p>
              <p style="margin:4px 0 0 0;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:#64748b;">Zoning</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Body copy -->
    <tr>
      <td style="padding:28px 28px 8px;">
        {body_html}
      </td>
    </tr>

    <!-- Photo grid -->
    <tr>
      <td style="padding:8px 28px 20px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          {photo_grid}
        </table>
      </td>
    </tr>

    <!-- Highlights -->
    <tr>
      <td style="padding:0 28px 28px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;">
          <tr><td style="padding:18px 20px;">
            <p style="margin:0 0 12px 0;font-size:11px;font-weight:bold;letter-spacing:0.1em;text-transform:uppercase;color:#94a3b8;">Property Highlights</p>
            <table cellpadding="0" cellspacing="0" border="0">
              <tr><td style="padding:4px 0;font-size:14px;color:#334155;">&#10003;&nbsp;&nbsp;Direct Highway 1416 frontage with high daily traffic count</td></tr>
              <tr><td style="padding:4px 0;font-size:14px;color:#334155;">&#10003;&nbsp;&nbsp;Minutes from Ellsworth Air Force Base</td></tr>
              <tr><td style="padding:4px 0;font-size:14px;color:#334155;">&#10003;&nbsp;&nbsp;Utilities available at site</td></tr>
              <tr><td style="padding:4px 0;font-size:14px;color:#334155;">&#10003;&nbsp;&nbsp;Ideal for retail, hospitality, or mixed-use development</td></tr>
              <tr><td style="padding:4px 0;font-size:14px;color:#334155;">&#10003;&nbsp;&nbsp;One of the fastest-growing markets in South Dakota</td></tr>
            </table>
          </td></tr>
        </table>
      </td>
    </tr>

    <!-- CTA -->
    <tr>
      <td align="center" style="padding:0 28px 32px;">
        <a href="mailto:arecblackhills@gmail.com?subject=Highway 1416 Inquiry" style="display:inline-block;background:#2563eb;color:#ffffff;font-size:14px;font-weight:bold;letter-spacing:0.06em;text-decoration:none;padding:14px 36px;border-radius:6px;">Request Full Package</a>
      </td>
    </tr>

    <!-- Footer -->
    <tr>
      <td style="background:#0f172a;padding:20px 28px;border-top:1px solid #1e293b;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td>
              <p style="margin:0;font-size:13px;font-weight:bold;color:#ffffff;">Kevin Andreson</p>
              <p style="margin:4px 0 0 0;font-size:12px;color:#64748b;">Keller Williams Realty Black Hills &nbsp;·&nbsp; <a href="mailto:arecblackhills@gmail.com" style="color:#60a5fa;text-decoration:none;">arecblackhills@gmail.com</a></p>
            </td>
            <td align="right">
              <p style="margin:0;font-size:11px;color:#475569;">Rapid City &amp; Black Hills, SD</p>
              <p style="margin:4px 0 0 0;font-size:11px;color:#334155;"><a href="https://christianschmaltz5-blip.github.io/Dashboard/" style="color:#475569;text-decoration:none;">arecblackhills.com</a></p>
            </td>
          </tr>
        </table>
        <p style="margin:16px 0 0 0;font-size:10px;color:#334155;line-height:1.6;">You are receiving this email because you have expressed interest in commercial real estate opportunities in the Black Hills region. To unsubscribe, reply with "unsubscribe" in the subject line.</p>
      </td>
    </tr>

  </table>
</td></tr>
</table>

</body>
</html>"""


def send(subject: str, html: str, dry_run: bool = False):
    if dry_run:
        print(f"\nDRY RUN — Subject: {subject}")
        print(f"Recipients ({len(RECIPIENTS)}): {', '.join(RECIPIENTS[:3])}...")
        print("HTML preview saved to preview_newsletter.html")
        with open("preview_newsletter.html", "w") as f:
            f.write(html)
        return

    sent = 0
    failed = []
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(FROM_EMAIL, GMAIL_APP_PASSWORD)
        for to in RECIPIENTS:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = f"Kevin Andreson — AREC Black Hills <{FROM_EMAIL}>"
            msg["To"]      = to
            msg["Reply-To"] = REPLY_TO
            msg.attach(MIMEText(html, "html"))
            try:
                smtp.sendmail(FROM_EMAIL, to, msg.as_string())
                sent += 1
                print(f"  ✓ {to}")
                time.sleep(0.3)  # stay within Gmail rate limits
            except Exception as e:
                failed.append((to, str(e)))
                print(f"  ✗ {to}: {e}")

    print(f"\nSent: {sent}/{len(RECIPIENTS)}")
    if failed:
        print("Failed:")
        for addr, err in failed:
            print(f"  {addr}: {err}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", default=None, help="Override email subject line")
    parser.add_argument("--message", default=None, help="Override body copy (use \\n\\n for paragraphs)")
    parser.add_argument("--dry-run", action="store_true", help="Build HTML and print stats without sending")
    args = parser.parse_args()

    month = datetime.now().strftime("%B %Y")
    subject = args.subject or f"{SUBJECT_PREFIX} — {month} Update"
    message = args.message.replace("\\n\\n", "\n\n") if args.message else DEFAULT_MESSAGE

    html = build_html(message)
    send(subject, html, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
