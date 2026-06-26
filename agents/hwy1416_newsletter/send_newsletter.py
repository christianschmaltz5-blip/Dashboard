#!/usr/bin/env python3
"""
Highway 1416, Box Elder — Newsletter Send Script
Usage:
  python3 send_newsletter.py                          # preview send to arecblackhills@gmail.com ONLY
  python3 send_newsletter.py --subject "Custom Title" --message "Update text here"
  python3 send_newsletter.py --dry-run                # build HTML + print stats, no emails sent
  python3 send_newsletter.py --send-all               # preview to Kevin FIRST, then full 32-person list
"""
import argparse
import base64
import io
import smtplib
import ssl
import time
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime

try:
    import requests as _requests
    from PIL import Image as _PILImage
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
        Table, TableStyle, HRFlowable,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    PDF_ENABLED = True
except ImportError:
    PDF_ENABLED = False


IMAGES_DIR = "images"  # local folder: agents/hwy1416_newsletter/images/

# Map LoopNet URLs → local filenames (drop the long hash prefix)
LOCAL_PHOTOS = [
    f"{IMAGES_DIR}/photo1.png",
    f"{IMAGES_DIR}/photo2.png",
    f"{IMAGES_DIR}/photo3.jpg",
    f"{IMAGES_DIR}/photo4.jpg",
    f"{IMAGES_DIR}/photo5.jpg",
    f"{IMAGES_DIR}/photo6.png",
]


def _fetch_image(url: str, local_path: str | None = None) -> io.BytesIO | None:
    import os
    # Try local file first
    if local_path and os.path.exists(local_path):
        with open(local_path, "rb") as f:
            return io.BytesIO(f.read())
    # Fall back to network (may be blocked by hotlink protection)
    try:
        r = _requests.get(url, timeout=12, verify=False, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return io.BytesIO(r.content)
    except Exception:
        return None

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


def build_pdf(message: str) -> bytes | None:
    if not PDF_ENABLED:
        return None
    import warnings
    warnings.filterwarnings("ignore")  # suppress requests SSL warnings
    try:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=letter,
            leftMargin=0.65*inch, rightMargin=0.65*inch,
            topMargin=0.6*inch, bottomMargin=0.6*inch,
        )
        W = letter[0] - 1.3*inch  # usable width

        # ── Colors ───────────────────────────────────────────────────────────
        DARK   = HexColor("#0f172a")
        BLUE   = HexColor("#2563eb")
        MUTED  = HexColor("#64748b")
        BODY   = HexColor("#334155")

        styles = getSampleStyleSheet()
        def style(name, **kw):
            return ParagraphStyle(name, parent=styles["Normal"], **kw)

        tag_style   = style("tag",   fontSize=8,  textColor=HexColor("#60a5fa"), spaceAfter=2)
        h1_style    = style("h1",    fontSize=22, textColor=HexColor("#ffffff"), leading=26, spaceAfter=4)
        sub_style   = style("sub",   fontSize=10, textColor=HexColor("#94a3b8"), spaceAfter=0)
        body_style  = style("body",  fontSize=10, textColor=BODY, leading=16, spaceAfter=10)
        label_style = style("lbl",   fontSize=7,  textColor=MUTED, alignment=TA_CENTER, spaceAfter=0)
        val_style   = style("val",   fontSize=16, textColor=HexColor("#ffffff"), alignment=TA_CENTER, spaceAfter=2)
        hl_style    = style("hl",    fontSize=9,  textColor=BODY, leading=14, spaceAfter=4)
        foot_style  = style("foot",  fontSize=8,  textColor=MUTED, spaceAfter=0)

        story = []
        month = datetime.now().strftime("%B %Y")

        # ── Header band (dark bg via table) ──────────────────────────────────
        header_data = [[
            Paragraph("ARECBLACKHILLS.COM — KELLER WILLIAMS REALTY BLACK HILLS",
                      style("hdr", fontSize=7, textColor=HexColor("#94a3b8"), alignment=TA_CENTER))
        ]]
        header_tbl = Table(header_data, colWidths=[W])
        header_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), DARK),
            ("TOPPADDING",    (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ("LEFTPADDING",   (0,0), (-1,-1), 10),
            ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ]))
        story.append(header_tbl)
        story.append(Spacer(1, 6))

        # ── Hero image ────────────────────────────────────────────────────────
        print("  Loading photos for PDF...")
        hero_buf = _fetch_image(PHOTOS[0], LOCAL_PHOTOS[0])
        if hero_buf:
            img = RLImage(hero_buf, width=W, height=3.0*inch)
            img.hAlign = "CENTER"
            story.append(img)
            story.append(Spacer(1, 0))

        # ── Title band ────────────────────────────────────────────────────────
        title_data = [[
            Paragraph(f"{month} Update", tag_style),
            ""
        ], [
            Paragraph("Highway 1416, Box Elder", h1_style),
            ""
        ], [
            Paragraph("Box Elder, SD 57719 &nbsp;·&nbsp; Commercial Land", sub_style),
            ""
        ]]
        title_tbl = Table(title_data, colWidths=[W, 0])
        title_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), DARK),
            ("TOPPADDING",    (0,0), (-1,-1), 3),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
            ("LEFTPADDING",   (0,0), (-1,-1), 12),
            ("RIGHTPADDING",  (0,0), (-1,-1), 12),
        ]))
        story.append(title_tbl)
        story.append(Spacer(1, 6))

        # ── Stats bar ─────────────────────────────────────────────────────────
        stats = [
            ("24.75", "ACRES"),
            ("$3.75M", "ASKING PRICE"),
            ("HWY", "FRONTAGE"),
            ("C-2", "ZONING"),
        ]
        stats_cells = [[Paragraph(v, val_style), Paragraph(l, label_style)] for v, l in stats]
        stats_row = [[cell for pair in stats_cells for cell in pair]]  # flatten
        # Build as 4-col table with val+label stacked
        stat_rows = [
            [Paragraph(v, val_style) for v, _ in stats],
            [Paragraph(l, label_style) for _, l in stats],
        ]
        stats_tbl = Table(stat_rows, colWidths=[W/4]*4)
        stats_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), HexColor("#1e293b")),
            ("TOPPADDING",    (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ("LINEBEFORE",    (1,0), (3,-1), 0.5, HexColor("#334155")),
        ]))
        story.append(stats_tbl)
        story.append(Spacer(1, 12))

        # ── Body copy ─────────────────────────────────────────────────────────
        for para in message.strip().split("\n\n"):
            if para.strip():
                story.append(Paragraph(para.strip(), body_style))
        story.append(Spacer(1, 8))

        # ── Photo grid (2 columns) ────────────────────────────────────────────
        grid_photos = list(zip(PHOTOS[1:], LOCAL_PHOTOS[1:]))
        grid_imgs = []
        for url, local in grid_photos:
            img_buf = _fetch_image(url, local)
            if img_buf:
                grid_imgs.append(RLImage(img_buf, width=(W/2)-4, height=1.6*inch))
            else:
                grid_imgs.append(Spacer((W/2)-4, 1.6*inch))

        for i in range(0, len(grid_imgs), 2):
            row = [grid_imgs[i], grid_imgs[i+1] if i+1 < len(grid_imgs) else ""]
            tbl = Table([row], colWidths=[W/2, W/2])
            tbl.setStyle(TableStyle([
                ("LEFTPADDING",   (0,0), (-1,-1), 0),
                ("RIGHTPADDING",  (0,0), (-1,-1), 0),
                ("TOPPADDING",    (0,0), (-1,-1), 4),
                ("BOTTOMPADDING", (0,0), (-1,-1), 0),
            ]))
            story.append(tbl)
        story.append(Spacer(1, 12))

        # ── Highlights ────────────────────────────────────────────────────────
        highlights = [
            "Direct Highway 1416 frontage with high daily traffic count",
            "Minutes from Ellsworth Air Force Base",
            "Utilities available at site",
            "Ideal for retail, hospitality, or mixed-use development",
            "One of the fastest-growing markets in South Dakota",
        ]
        hl_items = [[Paragraph(f"✓  {h}", hl_style)] for h in highlights]
        hl_tbl = Table(hl_items, colWidths=[W])
        hl_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), HexColor("#f8fafc")),
            ("TOPPADDING",    (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("LEFTPADDING",   (0,0), (-1,-1), 12),
            ("RIGHTPADDING",  (0,0), (-1,-1), 12),
            ("LINEBELOW",     (0,0), (-1,-2), 0.3, HexColor("#e2e8f0")),
        ]))
        story.append(hl_tbl)
        story.append(Spacer(1, 16))
        story.append(HRFlowable(width=W, thickness=0.5, color=HexColor("#e2e8f0")))
        story.append(Spacer(1, 8))

        # ── Footer ────────────────────────────────────────────────────────────
        story.append(Paragraph(
            "Kevin Andreson &nbsp;·&nbsp; Keller Williams Realty Black Hills &nbsp;·&nbsp; arecblackhills@gmail.com",
            foot_style
        ))
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "To unsubscribe, reply with \"unsubscribe\" in the subject line.",
            style("unsub", fontSize=7, textColor=HexColor("#94a3b8"))
        ))

        doc.build(story)
        kb = len(buf.getvalue()) // 1024
        print(f"  PDF ready: {kb}kb")
        return buf.getvalue()

    except Exception as e:
        print(f"  [warn] PDF generation failed: {e}")
        return None


def _send_one(smtp, subject: str, html: str, to: str, pdf_bytes: bytes | None = None):
    outer = MIMEMultipart("mixed")
    outer["Subject"] = subject
    outer["From"]    = f"Kevin Andreson — AREC Black Hills <{FROM_EMAIL}>"
    outer["To"]      = to
    outer["Reply-To"] = REPLY_TO

    # HTML body
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(html, "html"))
    outer.attach(alt)

    # PDF attachment
    if pdf_bytes:
        month = datetime.now().strftime("%B_%Y")
        part = MIMEBase("application", "pdf")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="Highway_1416_Box_Elder_{month}.pdf"')
        outer.attach(part)

    smtp.sendmail(FROM_EMAIL, to, outer.as_string())


def send(subject: str, html: str, message: str, dry_run: bool = False, send_all: bool = False):
    if dry_run:
        print(f"\nDRY RUN — Subject: {subject}")
        print(f"Would send preview to: {REPLY_TO}")
        if send_all:
            print(f"Would then send to full list ({len(RECIPIENTS)} recipients)")
        print("HTML preview saved to preview_newsletter.html")
        with open("preview_newsletter.html", "w") as f:
            f.write(html)
        if not PDF_ENABLED:
            print("PDF: reportlab/requests not installed — run: pip3 install reportlab Pillow requests")
        return

    # Generate PDF once, reuse for all sends
    pdf_bytes = None
    if PDF_ENABLED:
        print("Generating PDF attachment...")
        pdf_bytes = build_pdf(message)
    else:
        print("  [info] reportlab not installed — sending without PDF. Run: pip3 install reportlab Pillow requests")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(FROM_EMAIL, GMAIL_APP_PASSWORD)

        # Always send to Kevin first for review
        print(f"\n── Preview send ──────────────────────")
        try:
            _send_one(smtp, f"[PREVIEW] {subject}", html, REPLY_TO, pdf_bytes)
            print(f"  ✓ {REPLY_TO}")
        except Exception as e:
            print(f"  ✗ Preview failed: {e}")
            return

        if not send_all:
            print(f"\nPreview sent to {REPLY_TO}.")
            print("Review it, then run with --send-all to deliver to all 32 recipients.")
            return

        # Full list send
        print(f"\n── Full send ({len(RECIPIENTS)} recipients) ──────────")
        sent, failed = 0, []
        for to in RECIPIENTS:
            try:
                _send_one(smtp, subject, html, to, pdf_bytes)
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
    parser.add_argument("--subject",  default=None, help="Override email subject line")
    parser.add_argument("--message",  default=None, help="Override body copy (use \\n\\n for paragraphs)")
    parser.add_argument("--dry-run",  action="store_true", help="Build HTML and save preview, no emails sent")
    parser.add_argument("--send-all", action="store_true", help="After preview send to Kevin, deliver to all 32 recipients")
    args = parser.parse_args()

    month = datetime.now().strftime("%B %Y")
    subject = args.subject or f"{SUBJECT_PREFIX} — {month} Update"
    message = args.message.replace("\\n\\n", "\n\n") if args.message else DEFAULT_MESSAGE

    html = build_html(message)
    send(subject, html, message, dry_run=args.dry_run, send_all=args.send_all)


if __name__ == "__main__":
    main()
