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

# NOTE (2026-07-01): photo1.png is a stormwater/utility engineering overlay and
# photo6.jpg is a rough iPad screenshot of a planning sketch — neither is a
# customer-facing marketing photo, so they're excluded from HERO/LOCAL_PHOTOS
# below. photo2.png is the clean vector "Freedom Estates" site plan exhibit
# (has the Andreson Real Estate Co. logo) — used as its own PDF exhibit page,
# not in the photo grid. photo3-5.jpg are real aerial drone shots of the site.
HERO_LOCAL      = f"{IMAGES_DIR}/photo3.jpg"   # confirmed real aerial — PDF hero fallback
SITE_PLAN_LOCAL = f"{IMAGES_DIR}/photo2.png"   # Freedom Estates site plan exhibit

DEV_NAME           = "Freedom Estates"
DISTANCE_TO_EAFB   = "1.8 miles"   # from Exit 67, per the Freedom Estates site plan locator inset

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

ACRES        = 24.76
ASKING_PRICE = 3_750_000
LI_ACRES     = 7.30            # light industrial / commercial parcel
LI_PRICE     = 1_150_000
FRONTAGE_FT  = 1200   # matches the conceptual site plan on listing-newsletter.html
ZONING       = "C-2"
PRICE_PER_ACRE = round(ASKING_PRICE / ACRES)

# ── Design tokens ─────────────────────────────────────────────────────────────
# Palette remapped 2026-07-02 to the Freedom Estates artifact (prairie green /
# cream / terracotta). Variable NAMES kept for stability across build_html +
# build_pdf: NAVY = deep green, NAVY_2 = darker green, GOLD = wheat.
NAVY      = "#2b3720"
NAVY_2    = "#212c18"
GOLD      = "#d8a43a"
GOLD_DIM  = "#a9791c"
RUST      = "#a85431"
PRICE_CLR = "#b23a26"
PAPER     = "#f4efe1"
BODY_GRAY = "#3f3323"
MUTED     = "#6f6553"
LINE      = "#e3d9c0"
SERIF     = "Georgia,'Times New Roman',serif"

PHOTOS = [
    "https://images1.loopnet.com/i2/QGILchjqaRVCkLbafYze9QdMfuROFsVnu1AQ616h_KE/116/Highway-1416-Box-Elder-SD-Primary-Photo-1-LargeHighDefinition.png",
    "https://images1.loopnet.com/i2/28Vs7Jzi7XQFFHQ3sn6WydrFK3Pf0B8NEp338LX3Rsc/116/Highway-1416-Box-Elder-SD-Building-Photo-2-LargeHighDefinition.png",
    "https://images1.loopnet.com/i2/BkWayRvOg1L2SC1nvGsVXPmHFzbD9_qdHCWfa4fiquM/116/Highway-1416-Box-Elder-SD-Building-Photo-3-LargeHighDefinition.jpg",
    "https://images1.loopnet.com/i2/WO6DjGRPB0XgVIxIE82FbIVhHY_OnpSc7Q2tg3FpZ0M/116/Highway-1416-Box-Elder-SD-Building-Photo-4-LargeHighDefinition.jpg",
    "https://images1.loopnet.com/i2/KjFxxHAYpIOiUpkXKKhLNfhzhHw3qIziueht35_Fh2U/116/Highway-1416-Box-Elder-SD-Building-Photo-5-LargeHighDefinition.jpg",
    "https://images1.loopnet.com/i2/mMaKnCff4F3QSIofyudastA7AdLVFHTIn2ftqOOjYnk/116/Highway-1416-Box-Elder-SD-Building-Photo-6-LargeHighDefinition.png",
]

DEFAULT_MESSAGE = f"""
Two shovel-ready tracts on Highway 1416, {DISTANCE_TO_EAFB} from the Ellsworth Air Force
Base main gate at Exit 67 — the primary access corridor into the Black Hills region's
largest employer. Both sites are graded, permit-ready, and served by utilities on site,
with approximately 1,200 linear feet of highway frontage.

At the center is a 24.76-acre multi-family parcel ($3,750,000) within {DEV_NAME}, alongside
a 7.30-acre light industrial / commercial parcel ($1,150,000). The master-planned tract also
carries single-family and commercial phases and a future Douglas High School site directly
adjacent — rooftop growth that compounds the case for this corridor. Under the Investor
Flex-Option, the parcels can be acquired individually or as one cohesive tract — and with
zoning and utilities already in place, a buyer moves straight into site planning without
rezoning or annexation contingencies.
""".strip()

BROKER_QUOTE = (
    "“Box Elder is growing toward Ellsworth, not away from it. Frontage on this corridor "
    "doesn't come up often — worth a serious look before it's off the market.”"
)


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
    li_price_fmt = "$" + f"{LI_PRICE/1_000_000:.2f}".rstrip("0").rstrip(".") + "M"

    snapshot_rows = [
        ("Development", f"{DEV_NAME}, Box Elder"),
        ("Status", "Shovel-Ready — permits complete"),
        ("Multi-Family", f"{ACRES}± acres &middot; ${ASKING_PRICE:,}"),
        ("Light Industrial", f"{LI_ACRES}± acres &middot; ${LI_PRICE:,}"),
        ("Zoning", f"{ZONING} — Commercial"),
        ("Utilities", "On site"),
        ("Highway Frontage", f"~{FRONTAGE_FT:,} linear feet"),
        ("Proximity", f"{DISTANCE_TO_EAFB} from Ellsworth AFB (Exit 67)"),
        ("Access", "Direct frontage on Highway 1416 / I-90 corridor"),
        ("Adjacent Uses", "Single-family, commercial, future Douglas H.S. site"),
        ("Structure", "Investor Flex-Option — parcels or whole tract"),
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
<body style="margin:0;padding:0;background:#e6ddca;font-family:Arial,Helvetica,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#e6ddca;">
<tr><td align="center" style="padding:24px 12px;">

  <!-- Outer card -->
  <table width="640" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;background:{PAPER};border-radius:4px;overflow:hidden;box-shadow:0 4px 28px rgba(34,25,15,0.14);">

    <!-- Top bar -->
    <tr>
      <td style="background:{NAVY};padding:14px 28px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="font-size:13px;font-weight:bold;letter-spacing:0.06em;color:#ffffff;font-family:{SERIF};">Freedom Estates<span style="font-family:Arial,Helvetica,sans-serif;font-size:10px;font-weight:bold;letter-spacing:0.14em;text-transform:uppercase;color:#c8cdb6;">&nbsp;&nbsp;Box Elder, SD</span></td>
            <td align="right" style="font-size:10px;font-weight:bold;letter-spacing:0.16em;text-transform:uppercase;color:{NAVY};background:{GOLD};padding:5px 12px;border-radius:100px;">&#10003; Shovel-Ready</td>
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
        <p style="margin:0 0 8px 0;font-size:10px;font-weight:bold;letter-spacing:0.18em;text-transform:uppercase;color:{GOLD};">Multi-Family &amp; Commercial Development &middot; {month}</p>
        <p style="margin:0;font-family:{SERIF};font-size:28px;font-weight:bold;color:#ffffff;line-height:1.25;">Graded, permitted &mdash; <span style="color:{GOLD};font-style:italic;">ready to build.</span></p>
        <p style="margin:8px 0 0 0;font-size:13px;color:#c8cdb6;">{DEV_NAME} &nbsp;&middot;&nbsp; Highway 1416, Box Elder, SD 57719 &nbsp;&middot;&nbsp; Utilities On Site</p>
      </td>
    </tr>

    <!-- Stats bar -->
    <tr>
      <td style="background:{NAVY_2};padding:0;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td width="22%" align="center" style="padding:16px 6px;border-right:1px solid #3a4a2b;">
              <p style="margin:0;font-family:{SERIF};font-size:24px;font-weight:bold;color:#ffffff;">{ACRES}</p>
              <p style="margin:4px 0 0 0;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:{GOLD_DIM};">Multi-Family Ac.</p>
            </td>
            <td width="18%" align="center" style="padding:16px 6px;border-right:1px solid #3a4a2b;">
              <p style="margin:0;font-family:{SERIF};font-size:24px;font-weight:bold;color:{GOLD};">{price_fmt}</p>
              <p style="margin:4px 0 0 0;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:{GOLD_DIM};">MF Price</p>
            </td>
            <td width="20%" align="center" style="padding:16px 6px;border-right:1px solid #3a4a2b;">
              <p style="margin:0;font-family:{SERIF};font-size:24px;font-weight:bold;color:#ffffff;">{LI_ACRES}</p>
              <p style="margin:4px 0 0 0;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:{GOLD_DIM};">Light Ind. Ac.</p>
            </td>
            <td width="18%" align="center" style="padding:16px 6px;border-right:1px solid #3a4a2b;">
              <p style="margin:0;font-family:{SERIF};font-size:24px;font-weight:bold;color:{GOLD};">{li_price_fmt}</p>
              <p style="margin:4px 0 0 0;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:{GOLD_DIM};">LI Price</p>
            </td>
            <td width="22%" align="center" style="padding:16px 6px;">
              <p style="margin:0;font-family:{SERIF};font-size:24px;font-weight:bold;color:#ffffff;">Exit 67</p>
              <p style="margin:4px 0 0 0;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:{GOLD_DIM};">I-90 Access</p>
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

    <!-- Broker Quote -->
    <tr>
      <td style="padding:4px 28px 24px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-left:3px solid {GOLD};">
          <tr><td style="padding:2px 0 2px 18px;">
            <p style="margin:0;font-family:{SERIF};font-size:15px;font-style:italic;line-height:1.6;color:{NAVY};">{BROKER_QUOTE}</p>
            <p style="margin:8px 0 0 0;font-size:11px;font-weight:bold;letter-spacing:0.04em;color:{MUTED};">&mdash; Kevin Andreson, Keller Williams Realty Black Hills</p>
          </td></tr>
        </table>
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
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#ece4d0;border-radius:6px;border:1px solid {LINE};">
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
        <a href="mailto:kandreson@kw.com?subject=Freedom Estates — Request Offering Package" style="display:inline-block;background:{RUST};color:#ffffff;font-size:13px;font-weight:bold;letter-spacing:0.08em;text-transform:uppercase;text-decoration:none;padding:14px 36px;border-radius:3px;border:1px solid {GOLD};">Request Offering Package</a>
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
              <p style="margin:3px 0 0 0;font-size:11px;color:{GOLD_DIM};letter-spacing:0.04em;">Realtor &middot; Keller Williams Black Hills</p>
              <p style="margin:6px 0 0 0;font-size:11px;color:#c8cdb6;">(605) 646-5409 &nbsp;&middot;&nbsp; <a href="mailto:kandreson@kw.com" style="color:{GOLD};text-decoration:none;">kandreson@kw.com</a></p>
            </td>
            <td align="right" valign="top">
              <p style="margin:0;font-size:10px;color:#c8cdb6;">Rapid City &amp; Black Hills, SD</p>
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
    """Landscape one-pager matching the email's navy/gold institutional design —
    same color tokens (NAVY/NAVY_2/GOLD) and framing (offering summary, big-number
    stat grid, broker quote, confidentiality footer) as build_html()."""
    if not PDF_ENABLED:
        return None
    import warnings, os
    warnings.filterwarnings("ignore")

    try:
        buf = io.BytesIO()
        W, H = landscape(letter)   # 792 x 612 pt
        c = _rl_canvas.Canvas(buf, pagesize=(W, H))

        # ── Colors (match build_html's design tokens) ───────────────────────────
        PDF_NAVY   = HexColor(NAVY)
        PDF_NAVY_2 = HexColor(NAVY_2)
        PDF_GOLD   = HexColor(GOLD)
        PDF_GOLD_DIM = HexColor(GOLD_DIM)
        PDF_BODY   = HexColor(BODY_GRAY)
        PDF_MUTED  = HexColor(MUTED)
        LGRAY      = HexColor("#F8FAFC")
        WHITE      = white

        # ── Section heights (bottom → top) ───────────────────────────────────────
        FT_H = 76    # footer
        QT_H = 80    # broker quote
        SN_H = 90    # property snapshot facts
        ST_H = 85    # stat bar
        HD_H = 50    # top bar
        HR_H = H - FT_H - QT_H - SN_H - ST_H - HD_H   # hero (~260)

        ft_y = 0
        qt_y = FT_H
        sn_y = qt_y + QT_H
        st_y = sn_y + SN_H
        hr_y = st_y + ST_H
        hd_y = hr_y + HR_H   # == H - HD_H

        month = datetime.now().strftime("%B %Y")
        price_millions = f"{ASKING_PRICE/1_000_000:.2f}".rstrip("0").rstrip(".")
        price_fmt = f"${price_millions}M"
        price_per_acre_fmt = f"${PRICE_PER_ACRE/1000:.0f}K"

        # ── Helpers ───────────────────────────────────────────────────────────
        def rect(x, y, w, h, fill_color):
            c.setFillColor(fill_color)
            c.rect(x, y, w, h, fill=1, stroke=0)

        def text(txt, x, y, font, size, color=WHITE, align="left"):
            c.setFont(font, size)
            c.setFillColor(color)
            if align == "center":
                c.drawCentredString(x, y, txt)
            elif align == "right":
                c.drawRightString(x, y, txt)
            else:
                c.drawString(x, y, txt)

        def wrap_text(txt, font, size, max_width):
            """Greedy word-wrap: returns a list of lines that each fit max_width."""
            words = txt.split()
            lines, line = [], ""
            for w in words:
                trial = f"{line} {w}".strip()
                if c.stringWidth(trial, font, size) <= max_width:
                    line = trial
                else:
                    if line:
                        lines.append(line)
                    line = w
            if line:
                lines.append(line)
            return lines

        # ══════════════════════════════════════════════════════════════════════
        # TOP BAR (navy)
        # ══════════════════════════════════════════════════════════════════════
        rect(0, hd_y, W, HD_H, PDF_NAVY)
        text("KELLER WILLIAMS REALTY BLACK HILLS", 30, hd_y + HD_H * 0.4, "Helvetica-Bold", 11, WHITE)
        text("INVESTMENT OFFERING", W - 30, hd_y + HD_H * 0.4, "Helvetica-Bold", 10, PDF_GOLD, align="right")

        # ══════════════════════════════════════════════════════════════════════
        # HERO — aerial photo (right) + navy overlay panel (left) with headline
        # ══════════════════════════════════════════════════════════════════════
        PANEL_W = W * 0.40

        print("  Loading photos for PDF...")
        hero_buf = _fetch_image(PHOTOS[0], HERO_LOCAL)
        if hero_buf:
            c.drawImage(ImageReader(hero_buf), PANEL_W, hr_y,
                        width=W - PANEL_W, height=HR_H,
                        preserveAspectRatio=False, mask="auto")
        else:
            rect(PANEL_W, hr_y, W - PANEL_W, HR_H, PDF_NAVY_2)

        # Thin gold seam between panel and photo
        rect(PANEL_W - 3, hr_y, 3, HR_H, PDF_GOLD)

        # Navy overlay panel (left)
        rect(0, hr_y, PANEL_W, HR_H, PDF_NAVY)
        px = 30
        text(f"OFFERING SUMMARY · {month}".upper(), px, hr_y + HR_H - 40, "Helvetica-Bold", 9, PDF_GOLD)
        text(f"{ACRES}± ACRES", px, hr_y + HR_H * 0.62, "Times-Bold", 34, WHITE)
        text("ON THE ELLSWORTH AFB", px, hr_y + HR_H * 0.48, "Times-Bold", 22, WHITE)
        text("ACCESS CORRIDOR", px, hr_y + HR_H * 0.38, "Times-Bold", 22, WHITE)
        text(f"{DEV_NAME} · Highway 1416, Box Elder, SD 57719", px, hr_y + 34, "Helvetica", 10, HexColor("#9FB3C8"))
        text(f"Commercial Land · {ZONING} Zoning", px, hr_y + 20, "Helvetica", 10, HexColor("#9FB3C8"))

        # ══════════════════════════════════════════════════════════════════════
        # STAT BAR (navy_2) — matches the email's 5-stat grid
        # ══════════════════════════════════════════════════════════════════════
        rect(0, st_y, W, ST_H, PDF_NAVY_2)
        stats = [
            (f"{ACRES}", "ACRES"),
            (price_fmt, "ASKING PRICE"),
            (price_per_acre_fmt, "PER ACRE"),
            (f"{FRONTAGE_FT:,}'", "FRONTAGE"),
            (ZONING, "ZONING"),
        ]
        col_w = W / len(stats)
        for i, (big, label) in enumerate(stats):
            cx = col_w * i + col_w / 2
            text(big, cx, st_y + ST_H * 0.52, "Times-Bold", 28, WHITE, align="center")
            text(label, cx, st_y + ST_H * 0.2, "Helvetica-Bold", 8.5, PDF_GOLD_DIM, align="center")
            if i > 0:
                c.setStrokeColor(HexColor("#22405C"))
                c.setLineWidth(0.75)
                c.line(col_w * i, st_y + 10, col_w * i, st_y + ST_H - 10)

        # ══════════════════════════════════════════════════════════════════════
        # PROPERTY SNAPSHOT (light) — data facts, not adjectives
        # ══════════════════════════════════════════════════════════════════════
        rect(0, sn_y, W, SN_H, LGRAY)
        c.setStrokeColor(HexColor("#E2E8F0"))
        c.setLineWidth(0.75)
        c.line(0, sn_y, W, sn_y)
        c.line(0, sn_y + SN_H, W, sn_y + SN_H)

        facts = [
            ("DEVELOPMENT", f"{DEV_NAME}, Box Elder"),
            ("ZONING", f"{ZONING} — Commercial"),
            ("FRONTAGE", f"~{FRONTAGE_FT:,} linear feet"),
            ("UTILITIES", "Available at site"),
            ("PROXIMITY", f"{DISTANCE_TO_EAFB} to Ellsworth AFB"),
            ("ACCESS", "Direct Hwy 1416 / I-90 frontage"),
        ]
        col_w3 = W / len(facts)
        fact_font_size = 10
        for i, (label, val) in enumerate(facts):
            fx = col_w3 * i + 22
            usable_w = col_w3 - 34   # column width minus left padding + gutter to next divider
            text(label, fx, sn_y + SN_H * 0.72, "Helvetica-Bold", 8, PDF_MUTED)
            val_lines = wrap_text(val, "Helvetica-Bold", fact_font_size, usable_w)
            line_y = sn_y + SN_H * 0.48
            for ln in val_lines[:2]:
                text(ln, fx, line_y, "Helvetica-Bold", fact_font_size, PDF_NAVY)
                line_y -= fact_font_size + 3
            if i > 0:
                c.setStrokeColor(HexColor("#E2E8F0"))
                c.setLineWidth(0.75)
                c.line(col_w3 * i, sn_y + 12, col_w3 * i, sn_y + SN_H - 12)

        # ══════════════════════════════════════════════════════════════════════
        # BROKER QUOTE (white, gold rule)
        # ══════════════════════════════════════════════════════════════════════
        rect(0, qt_y, W, QT_H, WHITE)
        rect(30, qt_y + 10, 3, QT_H - 20, PDF_GOLD)
        quote_lines = wrap_text(BROKER_QUOTE, "Times-BoldItalic", 13, W - 96)
        line_y = qt_y + QT_H - 26
        for ln in quote_lines[:2]:
            text(ln, 48, line_y, "Times-BoldItalic", 13, PDF_NAVY)
            line_y -= 17
        text("— Kevin Andreson, Keller Williams Realty Black Hills", 48, qt_y + 14, "Helvetica-Bold", 9, PDF_MUTED)

        # ══════════════════════════════════════════════════════════════════════
        # FOOTER (navy, gold top rule)
        # ══════════════════════════════════════════════════════════════════════
        rect(0, ft_y, W, FT_H, PDF_NAVY)
        rect(0, ft_y + FT_H - 2, W, 2, PDF_GOLD)

        text("KEVIN ANDRESON", 30, ft_y + FT_H - 24, "Times-Bold", 15, WHITE)
        text("Commercial Real Estate Advisor", 30, ft_y + FT_H - 40, "Helvetica-Bold", 9, PDF_GOLD_DIM)
        text("Keller Williams Realty Black Hills · 605-646-5409 · arecblackhills@gmail.com", 30, ft_y + FT_H - 54, "Helvetica", 8.5, HexColor("#9FB3C8"))

        # QR Code — kept clear of the bottom disclaimer line
        try:
            qr = _qrcode.QRCode(box_size=3, border=1)
            qr.add_data("https://kwblackhills.com")
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="#0B1C2E", back_color="white")
            qr_buf = io.BytesIO()
            qr_img.save(qr_buf, format="PNG")
            qr_buf.seek(0)
            qr_size = 40
            qr_x = W - qr_size - 100
            qr_y = ft_y + FT_H - qr_size - 16
            c.drawImage(ImageReader(qr_buf), qr_x, qr_y, width=qr_size, height=qr_size)
            text("SCAN FOR", qr_x - 8, qr_y + qr_size - 12, "Helvetica-Bold", 7, HexColor("#9FB3C8"), align="right")
            text("KWBLACKHILLS.COM", qr_x - 8, qr_y + qr_size - 24, "Helvetica-Bold", 7, HexColor("#9FB3C8"), align="right")
        except Exception:
            pass

        text("Information believed reliable but not independently verified; not an offer to sell securities.",
             W / 2, ft_y + 9, "Helvetica", 6.5, HexColor("#5C7691"), align="center")

        # ══════════════════════════════════════════════════════════════════════
        # PAGE 2 — SITE PLAN EXHIBIT (the actual Freedom Estates plat, not a placeholder)
        # ══════════════════════════════════════════════════════════════════════
        if os.path.exists(SITE_PLAN_LOCAL):
            c.showPage()
            rect(0, 0, W, H, WHITE)
            rect(0, H - HD_H, W, HD_H, PDF_NAVY)
            text("KELLER WILLIAMS REALTY BLACK HILLS", 30, H - HD_H + HD_H * 0.4, "Helvetica-Bold", 11, WHITE)
            text("SITE PLAN EXHIBIT", W - 30, H - HD_H + HD_H * 0.4, "Helvetica-Bold", 10, PDF_GOLD, align="right")

            with open(SITE_PLAN_LOCAL, "rb") as f:
                sp_img = ImageReader(io.BytesIO(f.read()))
            sp_iw, sp_ih = sp_img.getSize()
            avail_w, avail_h = W - 60, H - HD_H - 50
            scale = min(avail_w / sp_iw, avail_h / sp_ih)
            draw_w, draw_h = sp_iw * scale, sp_ih * scale
            draw_x = (W - draw_w) / 2
            draw_y = (H - HD_H - draw_h) / 2 + 10
            c.drawImage(sp_img, draw_x, draw_y, width=draw_w, height=draw_h)

            text(f"{DEV_NAME} conceptual site plan — not to scale; subject to final engineering and regulatory approval.",
                 W / 2, 16, "Helvetica", 7.5, PDF_MUTED, align="center")

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
