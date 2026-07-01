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
    from reportlab.pdfgen import canvas as _rl_canvas
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor, white, black, Color
    from reportlab.lib.utils import ImageReader
    import qrcode as _qrcode
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
    f"{IMAGES_DIR}/photo6.jpg",
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

ACRES        = 24.75
ASKING_PRICE = 3_750_000
FRONTAGE_FT  = 1200   # matches the conceptual site plan on listing-newsletter.html
ZONING       = "C-2"
PRICE_PER_ACRE = round(ASKING_PRICE / ACRES)

# ── Design tokens (navy / gold institutional palette, serif headline) ─────────
NAVY      = "#0B1C2E"
NAVY_2    = "#14283D"
GOLD      = "#C9A961"
GOLD_DIM  = "#9C8557"
BODY_GRAY = "#334155"
MUTED     = "#64748B"
LINE      = "#E2E8F0"
SERIF     = "Georgia,'Times New Roman',serif"

PHOTOS = [
    "https://images1.loopnet.com/i2/QGILchjqaRVCkLbafYze9QdMfuROFsVnu1AQ616h_KE/116/Highway-1416-Box-Elder-SD-Primary-Photo-1-LargeHighDefinition.png",
    "https://images1.loopnet.com/i2/28Vs7Jzi7XQFFHQ3sn6WydrFK3Pf0B8NEp338LX3Rsc/116/Highway-1416-Box-Elder-SD-Building-Photo-2-LargeHighDefinition.png",
    "https://images1.loopnet.com/i2/BkWayRvOg1L2SC1nvGsVXPmHFzbD9_qdHCWfa4fiquM/116/Highway-1416-Box-Elder-SD-Building-Photo-3-LargeHighDefinition.jpg",
    "https://images1.loopnet.com/i2/WO6DjGRPB0XgVIxIE82FbIVhHY_OnpSc7Q2tg3FpZ0M/116/Highway-1416-Box-Elder-SD-Building-Photo-4-LargeHighDefinition.jpg",
    "https://images1.loopnet.com/i2/KjFxxHAYpIOiUpkXKKhLNfhzhHw3qIziueht35_Fh2U/116/Highway-1416-Box-Elder-SD-Building-Photo-5-LargeHighDefinition.jpg",
    "https://images1.loopnet.com/i2/mMaKnCff4F3QSIofyudastA7AdLVFHTIn2ftqOOjYnk/116/Highway-1416-Box-Elder-SD-Building-Photo-6-LargeHighDefinition.png",
]

DEFAULT_MESSAGE = """
24.75± acres of C-2 zoned commercial land fronting Highway 1416 in Box Elder, SD, with
approximately 1,200 linear feet of highway frontage and all utilities available at the site.
The parcel sits within minutes of the Ellsworth Air Force Base main gate, on the primary
corridor connecting the base to Box Elder and I-90.

Box Elder is one of the fastest-growing communities in South Dakota, driven by Ellsworth's
continued presence as the region's largest employer and steady residential expansion along
the I-90/Highway 1416 corridor. Zoning and utility access are in place — a buyer can move
directly into site planning without rezoning or annexation contingencies.
""".strip()


def build_html(message: str) -> str:
    month = datetime.now().strftime("%B %Y")
    photo_grid = ""
    grid_photos = PHOTOS[1:]  # hero is photo[0], rest go in grid
    for i in range(0, len(grid_photos), 2):
        left = grid_photos[i]
        right = grid_photos[i + 1] if i + 1 < len(grid_photos) else None
        right_td = f'<td width="50%" style="padding:4px 0 0 4px;"><img src="{right}" width="100%" style="display:block;border-radius:2px;" alt=""/></td>' if right else '<td width="50%"></td>'
        photo_grid += f"""
        <tr>
          <td width="50%" style="padding:4px 4px 0 0;"><img src="{left}" width="100%" style="display:block;border-radius:2px;" alt=""/></td>
          {right_td}
        </tr>"""

    # Format message paragraphs
    paras = [p.strip() for p in message.strip().split("\n\n") if p.strip()]
    body_html = "".join(f'<p style="margin:0 0 15px 0;font-size:14px;line-height:1.8;color:{BODY_GRAY};">{p}</p>' for p in paras)

    price_millions = f"{ASKING_PRICE/1_000_000:.2f}".rstrip("0").rstrip(".")
    price_fmt = f"${price_millions}M"
    price_per_acre_fmt = f"${PRICE_PER_ACRE/1000:.0f}K"

    snapshot_rows = [
        ("Acreage", f"{ACRES}± acres"),
        ("Zoning", f"{ZONING} — Commercial"),
        ("Highway Frontage", f"~{FRONTAGE_FT:,} linear feet"),
        ("Utilities", "Available at site"),
        ("Proximity", "Minutes from Ellsworth AFB main gate"),
        ("Access", "Direct frontage on Highway 1416 / I-90 corridor"),
    ]
    snapshot_html = "".join(
        f"""<tr>
          <td style="padding:10px 0;border-bottom:1px solid {LINE};font-size:11px;font-weight:bold;letter-spacing:0.06em;text-transform:uppercase;color:{MUTED};width:42%;">{label}</td>
          <td style="padding:10px 0;border-bottom:1px solid {LINE};font-size:13px;color:{BODY_GRAY};">{val}</td>
        </tr>""" for label, val in snapshot_rows
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head>
<body style="margin:0;padding:0;background:#eef1f5;font-family:Arial,Helvetica,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#eef1f5;">
<tr><td align="center" style="padding:24px 12px;">

  <!-- Outer card -->
  <table width="640" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;background:#ffffff;border-radius:4px;overflow:hidden;box-shadow:0 4px 28px rgba(11,28,46,0.12);">

    <!-- Top bar -->
    <tr>
      <td style="background:{NAVY};padding:14px 28px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="font-size:11px;font-weight:bold;letter-spacing:0.14em;text-transform:uppercase;color:#ffffff;">Keller Williams Realty Black Hills</td>
            <td align="right" style="font-size:10px;font-weight:bold;letter-spacing:0.18em;text-transform:uppercase;color:{GOLD};">Investment Offering</td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Hero image -->
    <tr>
      <td style="padding:0;">
        <img src="{PHOTOS[0]}" width="640" style="display:block;width:100%;max-height:320px;object-fit:cover;" alt="Highway 1416, Box Elder SD"/>
      </td>
    </tr>
    <tr><td style="height:3px;background:{GOLD};line-height:3px;font-size:0;">&nbsp;</td></tr>

    <!-- Title band -->
    <tr>
      <td style="background:{NAVY};padding:24px 28px 22px;">
        <p style="margin:0 0 8px 0;font-size:10px;font-weight:bold;letter-spacing:0.18em;text-transform:uppercase;color:{GOLD};">Offering Summary &middot; {month}</p>
        <p style="margin:0;font-family:{SERIF};font-size:25px;font-weight:bold;color:#ffffff;line-height:1.3;">{ACRES}&plusmn; Acres &mdash; Highway 1416 Growth Corridor</p>
        <p style="margin:8px 0 0 0;font-size:13px;color:#9FB3C8;">Box Elder, SD 57719 &nbsp;&middot;&nbsp; Commercial Land &nbsp;&middot;&nbsp; {ZONING} Zoning</p>
      </td>
    </tr>

    <!-- Stats bar -->
    <tr>
      <td style="background:{NAVY_2};padding:0;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td width="20%" align="center" style="padding:16px 6px;border-right:1px solid #22405C;">
              <p style="margin:0;font-family:{SERIF};font-size:19px;font-weight:bold;color:#ffffff;">{ACRES}</p>
              <p style="margin:4px 0 0 0;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:{GOLD_DIM};">Acres</p>
            </td>
            <td width="20%" align="center" style="padding:16px 6px;border-right:1px solid #22405C;">
              <p style="margin:0;font-family:{SERIF};font-size:19px;font-weight:bold;color:#ffffff;">{price_fmt}</p>
              <p style="margin:4px 0 0 0;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:{GOLD_DIM};">Asking Price</p>
            </td>
            <td width="20%" align="center" style="padding:16px 6px;border-right:1px solid #22405C;">
              <p style="margin:0;font-family:{SERIF};font-size:19px;font-weight:bold;color:#ffffff;">{price_per_acre_fmt}</p>
              <p style="margin:4px 0 0 0;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:{GOLD_DIM};">Per Acre</p>
            </td>
            <td width="20%" align="center" style="padding:16px 6px;border-right:1px solid #22405C;">
              <p style="margin:0;font-family:{SERIF};font-size:19px;font-weight:bold;color:#ffffff;">{FRONTAGE_FT:,}'</p>
              <p style="margin:4px 0 0 0;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:{GOLD_DIM};">Frontage</p>
            </td>
            <td width="20%" align="center" style="padding:16px 6px;">
              <p style="margin:0;font-family:{SERIF};font-size:19px;font-weight:bold;color:#ffffff;">{ZONING}</p>
              <p style="margin:4px 0 0 0;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:{GOLD_DIM};">Zoning</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Investment Thesis -->
    <tr>
      <td style="padding:28px 28px 6px;">
        <p style="margin:0 0 12px 0;font-family:{SERIF};font-size:15px;font-weight:bold;color:{NAVY};">Investment Thesis</p>
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

    <!-- Property Snapshot -->
    <tr>
      <td style="padding:0 28px 28px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F8FAFC;border-radius:6px;border:1px solid {LINE};">
          <tr><td style="padding:18px 22px 6px;">
            <p style="margin:0 0 4px 0;font-size:10px;font-weight:bold;letter-spacing:0.14em;text-transform:uppercase;color:{MUTED};">Property Snapshot</p>
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              {snapshot_html}
            </table>
          </td></tr>
        </table>
      </td>
    </tr>

    <!-- CTA -->
    <tr>
      <td align="center" style="padding:0 28px 12px;">
        <a href="mailto:arecblackhills@gmail.com?subject=Highway 1416 Offering — Request Package" style="display:inline-block;background:{NAVY};color:#ffffff;font-size:13px;font-weight:bold;letter-spacing:0.08em;text-transform:uppercase;text-decoration:none;padding:14px 36px;border-radius:3px;border:1px solid {GOLD};">Request Offering Package</a>
      </td>
    </tr>
    <tr>
      <td align="center" style="padding:0 28px 30px;">
        <p style="margin:0;font-size:11px;color:{MUTED};">Site plan, comparable sales, and full due diligence package available upon request.</p>
      </td>
    </tr>

    <!-- Footer -->
    <tr>
      <td style="background:{NAVY};padding:22px 28px;border-top:2px solid {GOLD};">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td>
              <p style="margin:0;font-family:{SERIF};font-size:14px;font-weight:bold;color:#ffffff;">Kevin Andreson</p>
              <p style="margin:3px 0 0 0;font-size:11px;color:{GOLD_DIM};letter-spacing:0.04em;">Commercial Real Estate Advisor</p>
              <p style="margin:6px 0 0 0;font-size:11px;color:#9FB3C8;">Keller Williams Realty Black Hills &nbsp;&middot;&nbsp; <a href="mailto:arecblackhills@gmail.com" style="color:{GOLD};text-decoration:none;">arecblackhills@gmail.com</a></p>
            </td>
            <td align="right" valign="top">
              <p style="margin:0;font-size:10px;color:#9FB3C8;">Rapid City &amp; Black Hills, SD</p>
              <p style="margin:4px 0 0 0;font-size:10px;"><a href="https://christianschmaltz5-blip.github.io/Dashboard/" style="color:#9FB3C8;text-decoration:none;">kwblackhills.com</a></p>
            </td>
          </tr>
        </table>
        <p style="margin:16px 0 0 0;font-size:9px;color:#5C7691;line-height:1.7;">The information contained herein has been obtained from sources believed reliable but has not been independently verified; no representation is made as to its accuracy or completeness. This is not an offer to sell securities. You are receiving this email because you have expressed interest in commercial real estate opportunities in the Black Hills region. To unsubscribe, reply with "unsubscribe" in the subject line.</p>
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
    import warnings, os
    warnings.filterwarnings("ignore")

    try:
        buf = io.BytesIO()
        W, H = landscape(letter)   # 792 x 612 pt
        c = _rl_canvas.Canvas(buf, pagesize=(W, H))

        # ── Colors ────────────────────────────────────────────────────────────
        RED    = HexColor("#8B1A1A")
        BLACK  = HexColor("#1C1C1C")
        LGRAY  = HexColor("#E4E4E4")
        WHITE  = white

        # ── Section heights (bottom → top) ────────────────────────────────────
        FT_H   = 72    # footer
        FE_H   = 62    # features
        UT_H   = 82    # utilities
        HR_H   = 196   # hero
        HD_H   = H - FT_H - FE_H - UT_H - HR_H   # header (~200)

        ft_y = 0
        fe_y = FT_H
        ut_y = fe_y + FE_H
        hr_y = ut_y + UT_H
        hd_y = hr_y + HR_H

        # ── Helpers ───────────────────────────────────────────────────────────
        def rect(x, y, w, h, fill_color, stroke=False):
            c.setFillColor(fill_color)
            c.rect(x, y, w, h, fill=1, stroke=1 if stroke else 0)

        def text(txt, x, y, font, size, color=WHITE, align="left"):
            c.setFont(font, size)
            c.setFillColor(color)
            if align == "center":
                c.drawCentredString(x, y, txt)
            elif align == "right":
                c.drawRightString(x, y, txt)
            else:
                c.drawString(x, y, txt)

        # ══════════════════════════════════════════════════════════════════════
        # HEADER (white)
        # ══════════════════════════════════════════════════════════════════════
        rect(0, hd_y, W, HD_H, WHITE)

        # Left logo area — mountain peaks drawn as filled polygons
        mx, my = 30, hd_y + 55
        mscale = 1.15
        def peak(pts):
            p = c.beginPath()
            p.moveTo(pts[0][0]*mscale+mx, pts[0][1]*mscale+my)
            for px, py in pts[1:]:
                p.lineTo(px*mscale+mx, py*mscale+my)
            p.close()
            c.drawPath(p, fill=1, stroke=0)

        c.setFillColor(HexColor("#2C2C2C"))
        peak([(0,0),(25,65),(50,0)])        # left peak
        peak([(35,0),(65,80),(95,0)])       # center peak (tallest)
        peak([(75,0),(100,55),(125,0)])     # right peak

        # Snow caps (white triangles on top)
        c.setFillColor(WHITE)
        peak([(18,42),(25,65),(32,42)])
        peak([(55,56),(65,80),(75,56)])
        peak([(93,38),(100,55),(107,38)])

        # Horizontal rule under mountains
        c.setStrokeColor(HexColor("#1C1C1C"))
        c.setLineWidth(1.5)
        logo_text_x = 30
        logo_text_y = hd_y + 38
        c.line(logo_text_x, logo_text_y + 11, logo_text_x + 185, logo_text_y + 11)

        text("KEVIN ANDRESON", logo_text_x, logo_text_y, "Helvetica-Bold", 14, BLACK)

        c.setLineWidth(0.8)
        c.line(logo_text_x, logo_text_y - 3, logo_text_x + 185, logo_text_y - 3)

        # "— COMPANY —" spaced
        text("C O M P A N Y", logo_text_x + 28, logo_text_y - 14, "Helvetica", 8, BLACK)

        # KW branding
        text("kw", logo_text_x, logo_text_y - 32, "Helvetica-Bold", 15, HexColor("#CC0000"))
        text("BLACK HILLS", logo_text_x + 24, logo_text_y - 28, "Helvetica-Bold", 11, BLACK)
        text("KELLER WILLIAMS. REALTY", logo_text_x + 24, logo_text_y - 39, "Helvetica", 6.5, BLACK)

        # Vertical divider
        c.setStrokeColor(HexColor("#CCCCCC"))
        c.setLineWidth(1)
        divX = W * 0.42
        c.line(divX, hd_y + 18, divX, hd_y + HD_H - 18)

        # Right: Headline
        hx = divX + 28
        text("COMMERCIAL LAND", hx, hd_y + HD_H*0.56, "Helvetica-Bold", 42, BLACK)
        text("FOR", hx, hd_y + HD_H*0.28, "Helvetica-Bold", 42, BLACK)
        # "SALE" in red — measure "FOR " width to position
        c.setFont("Helvetica-Bold", 42)
        for_w = c.stringWidth("FOR ", "Helvetica-Bold", 42)
        text("SALE", hx + for_w, hd_y + HD_H*0.28, "Helvetica-Bold", 42, RED)

        # ══════════════════════════════════════════════════════════════════════
        # HERO — left red band + right aerial photo
        # ══════════════════════════════════════════════════════════════════════
        SPLIT  = W * 0.41
        DIAG   = 28   # diagonal offset

        # Dark red polygon (diagonal right edge)
        c.setFillColor(RED)
        p = c.beginPath()
        p.moveTo(0, hr_y)
        p.lineTo(SPLIT + DIAG, hr_y)
        p.lineTo(SPLIT - DIAG, hr_y + HR_H)
        p.lineTo(0, hr_y + HR_H)
        p.close()
        c.drawPath(p, fill=1, stroke=0)

        # Hero photo (right side)
        print("  Loading photos for PDF...")
        hero_buf = _fetch_image(PHOTOS[0], LOCAL_PHOTOS[0])
        if hero_buf:
            img_x = SPLIT - DIAG
            c.drawImage(ImageReader(hero_buf), img_x, hr_y,
                        width=W - img_x, height=HR_H,
                        preserveAspectRatio=False, mask="auto")

        # Big acreage number
        c.setFillColor(WHITE)
        c.setFont("Helvetica-BoldOblique", 82)
        c.drawString(14, hr_y + HR_H * 0.44, "24.75")
        c.setFont("Helvetica-BoldOblique", 62)
        c.drawString(14, hr_y + HR_H * 0.10, "ACRES")

        # Price tag below acreage
        c.setFont("Helvetica-Bold", 16)
        c.setFillColor(HexColor("#FFCCCC"))
        c.drawString(18, hr_y + HR_H * 0.04 - 2, "$3,750,000")

        # ══════════════════════════════════════════════════════════════════════
        # UTILITIES ROW (light gray)
        # ══════════════════════════════════════════════════════════════════════
        rect(0, ut_y, W, UT_H, LGRAY)

        utils = [
            ("ALL UTILITIES", "TO SITE"),
            ("NATURAL", "GAS"),
            ("WEST RIVER", "ELECTRIC"),
            ("CITY WATER", "& SEWER"),
            ("ZONED", "COMMERCIAL"),
        ]
        col_w = W / len(utils)
        icon_syms = ["*", "*", "~", "o", "#"]   # placeholders for circle content

        for i, (l1, l2) in enumerate(utils):
            cx = col_w * i + col_w / 2
            cy_circle = ut_y + UT_H * 0.72
            # Black filled circle
            c.setFillColor(BLACK)
            c.circle(cx, cy_circle, 16, fill=1, stroke=0)
            # White line icon (simplified)
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(cx, cy_circle - 4, str(i + 1))
            # Label lines
            c.setFillColor(BLACK)
            c.setFont("Helvetica-Bold", 8.5)
            c.drawCentredString(cx, ut_y + UT_H * 0.35, l1)
            c.setFont("Helvetica", 7.5)
            c.drawCentredString(cx, ut_y + UT_H * 0.15, l2)
            # Column dividers
            if i > 0:
                c.setStrokeColor(HexColor("#BBBBBB"))
                c.setLineWidth(0.5)
                c.line(col_w * i, ut_y + 8, col_w * i, ut_y + UT_H - 8)

        # ══════════════════════════════════════════════════════════════════════
        # FEATURES ROW (dark)
        # ══════════════════════════════════════════════════════════════════════
        rect(0, fe_y, W, FE_H, BLACK)

        features = [
            ("EXCELLENT VISIBILITY", "HIGH TRAFFIC CORRIDOR EXPOSURE"),
            ("DIRECT HWY 1416 ACCESS", "PRIME HIGHWAY FRONTAGE FOR BUSINESS GROWTH"),
        ]
        col_w2 = W / 2
        for i, (title, sub) in enumerate(features):
            cx = col_w2 * i + col_w2 / 2
            # Icon circle
            ic_x = col_w2 * i + 36
            ic_y = fe_y + FE_H / 2
            c.setFillColor(HexColor("#333333"))
            c.circle(ic_x, ic_y, 18, fill=1, stroke=0)
            c.setStrokeColor(WHITE)
            c.setLineWidth(1.5)
            if i == 0:  # eye-like shape
                c.circle(ic_x, ic_y, 7, fill=0, stroke=1)
                c.setFillColor(WHITE)
                c.circle(ic_x, ic_y, 3, fill=1, stroke=0)
            else:  # road lines
                c.setLineWidth(2)
                c.line(ic_x - 6, ic_y + 8, ic_x, ic_y - 8)
                c.line(ic_x + 6, ic_y + 8, ic_x, ic_y - 8)
            # Text
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(ic_x + 28, fe_y + FE_H * 0.6, title)
            c.setFont("Helvetica", 8)
            c.setFillColor(HexColor("#AAAAAA"))
            c.drawString(ic_x + 28, fe_y + FE_H * 0.28, sub)
            # Center divider
            if i == 0:
                c.setStrokeColor(HexColor("#3A3A3A"))
                c.setLineWidth(1)
                c.line(W / 2, fe_y + 10, W / 2, fe_y + FE_H - 10)

        # ══════════════════════════════════════════════════════════════════════
        # FOOTER (dark red)
        # ══════════════════════════════════════════════════════════════════════
        rect(0, ft_y, W, FT_H, RED)

        # Phone icon circle
        c.setFillColor(HexColor("#6B0000"))
        c.circle(30, ft_y + FT_H / 2, 20, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(30, ft_y + FT_H / 2 - 5, "t")

        # Contact info
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(58, ft_y + FT_H * 0.78, "CONTACT")
        c.setFont("Helvetica-Bold", 17)
        c.drawString(58, ft_y + FT_H * 0.48, "KEVIN ANDRESON")
        c.setFont("Helvetica-Bold", 13)
        c.drawString(58, ft_y + FT_H * 0.18, "605-646-5409")

        # Center divider
        c.setStrokeColor(HexColor("#6B0000"))
        c.setLineWidth(1)
        c.line(W * 0.38, ft_y + 8, W * 0.38, ft_y + FT_H - 8)

        # Globe icon + website
        c.setFillColor(HexColor("#6B0000"))
        c.circle(W * 0.5, ft_y + FT_H / 2, 20, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(W * 0.5, ft_y + FT_H / 2 - 5, "w")
        c.setFont("Helvetica-Bold", 13)
        c.drawCentredString(W * 0.62, ft_y + FT_H / 2 - 4, "KWBLACKHILLS.COM")

        # QR Code
        try:
            qr = _qrcode.QRCode(box_size=3, border=1)
            qr.add_data("https://kwblackhills.com")
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")
            qr_buf = io.BytesIO()
            qr_img.save(qr_buf, format="PNG")
            qr_buf.seek(0)
            qr_size = FT_H - 10
            c.drawImage(ImageReader(qr_buf), W - qr_size - 60, ft_y + 5,
                        width=qr_size, height=qr_size)
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", 7)
            c.drawCentredString(W - 30, ft_y + FT_H * 0.65, "SCAN FOR")
            c.drawCentredString(W - 30, ft_y + FT_H * 0.45, "DETAILS")
        except Exception:
            pass

        c.save()
        kb = len(buf.getvalue()) // 1024
        print(f"  PDF ready: {kb}kb")
        return buf.getvalue()

    except Exception as e:
        import traceback
        print(f"  [warn] PDF generation failed: {e}")
        traceback.print_exc()
        return None


def _send_one(smtp, subject: str, html: str, to: str, pdf_bytes: bytes | None = None):
    outer = MIMEMultipart("mixed")
    outer["Subject"] = subject
    outer["From"]    = f"Kevin Andreson | Keller Williams Black Hills <{FROM_EMAIL}>"
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
