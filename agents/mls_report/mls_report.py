"""
Market Report Agent — Kevin Andreson
Data sources: Zillow Research (5 series + 3 price tiers) + FRED (mortgage rates)
Run:  python3 mls_report.py          ← preview only (saves preview_report.html)
      python3 mls_report.py --send   ← preview + email
"""

import requests
import pandas as pd
import io
import json
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

DASHBOARD_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../js/market-data.js")

from config import (
    FRED_API_KEY, FROM_EMAIL, TO_EMAIL, GMAIL_APP_PASSWORD,
    TARGET_CITIES, TARGET_STATE, MARKET_LABEL,
    PRICE_BANDS, MLS_STATUSES, MLS_DETAIL_CATEGORIES,
)

PREVIEW_FILE = "preview_report.html"

# ── Zillow public CSV endpoints (all verified live) ──────────────────────────
ZILLOW_URLS = {
    "zhvi":         "https://files.zillowstatic.com/research/public_csvs/zhvi/City_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
    "sale_price":   "https://files.zillowstatic.com/research/public_csvs/median_sale_price/City_median_sale_price_uc_sfrcondo_sm_month.csv",
    "inventory":    "https://files.zillowstatic.com/research/public_csvs/invt_fs/City_invt_fs_uc_sfrcondo_sm_month.csv",
    "new_listings": "https://files.zillowstatic.com/research/public_csvs/new_listings/City_new_listings_uc_sfrcondo_sm_month.csv",
    "pct_above":    "https://files.zillowstatic.com/research/public_csvs/pct_sold_above_list/City_pct_sold_above_list_uc_sfrcondo_sm_month.csv",
}

# ZHVI by bedroom count — price-band proxy (all verified live for Rapid City)
_BR = "https://files.zillowstatic.com/research/public_csvs/zhvi/City_zhvi_bdrmcnt_{n}_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"
ZILLOW_TIER_URLS = {
    "1 BR  (~$100K–$250K)":  _BR.format(n=1),
    "2 BR  (~$250K–$320K)":  _BR.format(n=2),
    "3 BR  (~$320K–$400K)":  _BR.format(n=3),
    "4 BR  (~$400K–$500K)":  _BR.format(n=4),
    "5 BR+ (~$500K+)":       _BR.format(n=5),
}


# ── DATA FETCHERS ────────────────────────────────────────────────────────────

def get_mortgage_rates():
    """Pull 30-yr and 15-yr fixed rates from FRED."""
    results = {}
    for series, label in [("MORTGAGE30US", "30yr"), ("MORTGAGE15US", "15yr")]:
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series}&api_key={FRED_API_KEY}"
            "&sort_order=desc&limit=2&file_type=json"
        )
        obs = requests.get(url, timeout=15).json()["observations"]
        curr = float(obs[0]["value"])
        prev = float(obs[1]["value"])
        results[label] = {"rate": curr, "change": round(curr - prev, 2)}
    return results


def _load_zillow_series(url):
    """Download a Zillow CSV and return rows filtered to target cities."""
    r = requests.get(url, timeout=60)
    df = pd.read_csv(io.StringIO(r.text), low_memory=False)
    df = df[df["RegionName"].isin(TARGET_CITIES) & (df["State"] == TARGET_STATE)]
    return df


def _latest_two(df):
    """Return column names for the last two date periods."""
    date_cols = [c for c in df.columns if c[:4].isdigit()]
    return date_cols[-2], date_cols[-1]


def get_zillow_data():
    """Pull all 5 Zillow series and merge into one dict per city."""
    print("  Fetching Zillow home values (ZHVI)...")
    zhvi_df = _load_zillow_series(ZILLOW_URLS["zhvi"])
    print("  Fetching Zillow median sale prices...")
    sale_df = _load_zillow_series(ZILLOW_URLS["sale_price"])
    print("  Fetching Zillow active inventory...")
    inv_df  = _load_zillow_series(ZILLOW_URLS["inventory"])
    print("  Fetching Zillow new listings...")
    new_df  = _load_zillow_series(ZILLOW_URLS["new_listings"])
    print("  Fetching Zillow % sold above list...")
    above_df = _load_zillow_series(ZILLOW_URLS["pct_above"])

    cities_data = {}
    for city in TARGET_CITIES:
        row = {}

        zr = zhvi_df[zhvi_df["RegionName"] == city]
        if not zr.empty:
            p, c = _latest_two(zr)
            curr, prev = zr.iloc[0][c], zr.iloc[0][p]
            row["zhvi"]        = curr
            row["zhvi_change"] = round(((curr - prev) / prev) * 100, 1) if prev else 0

        sr = sale_df[sale_df["RegionName"] == city]
        if not sr.empty:
            p, c = _latest_two(sr)
            curr, prev = sr.iloc[0][c], sr.iloc[0][p]
            row["sale_price"]        = curr
            row["sale_price_change"] = round(((curr - prev) / prev) * 100, 1) if prev else 0

        ir = inv_df[inv_df["RegionName"] == city]
        if not ir.empty:
            p, c = _latest_two(ir)
            curr, prev = ir.iloc[0][c], ir.iloc[0][p]
            row["inventory"]        = curr
            row["inventory_change"] = round(curr - prev)

        nr = new_df[new_df["RegionName"] == city]
        if not nr.empty:
            _, c = _latest_two(nr)
            row["new_listings"] = nr.iloc[0][c]

        ar = above_df[above_df["RegionName"] == city]
        if not ar.empty:
            _, c = _latest_two(ar)
            row["pct_above"] = ar.iloc[0][c]

        if row:
            cities_data[city] = row

    return cities_data


def get_zhvi_trend(city="Rapid City", n=7):
    """Pull last n months of ZHVI for Rapid City trend chart."""
    print(f"  Fetching {n}-month ZHVI trend for {city}...")
    df = _load_zillow_series(ZILLOW_URLS["zhvi"])
    date_cols = sorted([c for c in df.columns if c[:4].isdigit()])
    row = df[df["RegionName"] == city]
    if row.empty:
        return []
    monthly = []
    for col in date_cols[-n:]:
        val = row.iloc[0][col]
        if pd.notna(val):
            monthly.append((col, float(val)))
    return monthly


def get_zhvi_tiers(city="Rapid City"):
    """Pull low / mid / high ZHVI tiers as a price-band proxy for Rapid City."""
    print("  Fetching price tier data (low / core / premium)...")
    tiers = {}
    for tier_label, url in ZILLOW_TIER_URLS.items():
        try:
            r = requests.get(url, timeout=60)
            df = pd.read_csv(io.StringIO(r.text), low_memory=False)
            df = df[df["RegionName"] == city]
            if df.empty:
                continue
            p, c = _latest_two(df)
            curr, prev = df.iloc[0][c], df.iloc[0][p]
            tiers[tier_label] = {
                "value":  float(curr),
                "change": round(((float(curr) - float(prev)) / float(prev)) * 100, 1) if prev else 0,
            }
        except Exception as e:
            print(f"    Tier '{tier_label}' skipped: {e}")
    return tiers


# ── FORMATTERS ───────────────────────────────────────────────────────────────

def fc(val):
    try:    return f"${float(val):,.0f}"
    except: return "N/A"

def fi(val):
    try:    return f"{int(float(val)):,}"
    except: return "N/A"

def fpct(val):
    try:
        v = float(val)
        arrow = "▲" if v >= 0 else "▼"
        color = "#38a169" if v >= 0 else "#e53e3e"
        return f'<span style="color:{color};font-weight:700;">{arrow} {abs(v):.1f}%</span>'
    except:
        return "N/A"

def frate_change(change):
    if change > 0:
        return f'<span style="color:#e53e3e;">▲ {abs(change):.2f}% WoW</span>'
    elif change < 0:
        return f'<span style="color:#38a169;">▼ {abs(change):.2f}% WoW</span>'
    return '<span style="color:#718096;">— unchanged</span>'


# ── CHART BUILDER ────────────────────────────────────────────────────────────

def build_bar_chart_html(monthly_data, title="6-Month Home Value Trend — Rapid City"):
    """Email-compatible bar chart using inline HTML table cells."""
    if len(monthly_data) < 2:
        return ""

    values = [v for _, v in monthly_data]
    labels = []
    for d, _ in monthly_data:
        try:
            labels.append(datetime.strptime(d[:7], "%Y-%m").strftime("%b '%y"))
        except Exception:
            labels.append(d[:7])

    min_v   = min(values) * 0.993
    max_v   = max(values)
    v_range = (max_v - min_v) if max_v != min_v else 1
    max_h   = 72

    bars = ""
    for i, (label, val) in enumerate(zip(labels, values)):
        bh      = max(4, int(((val - min_v) / v_range) * max_h))
        is_last = (i == len(values) - 1)
        color   = "#0f2942" if is_last else "#1d7eea"
        opacity = "1.0" if is_last else "0.55"
        bars += f"""
        <td style="text-align:center;vertical-align:bottom;padding:0 5px;">
          <div style="font-size:8px;color:#718096;margin-bottom:3px;
            font-family:Arial,sans-serif;">${val/1000:.0f}K</div>
          <div style="background:{color};height:{bh}px;width:36px;margin:0 auto;
            border-radius:3px 3px 0 0;opacity:{opacity};"></div>
          <div style="font-size:8px;color:#a0aec0;margin-top:5px;
            font-family:Arial,sans-serif;">{label}</div>
        </td>"""

    return f"""
    <div style="margin:18px 0 24px;">
      <div style="font-size:10px;font-weight:700;color:#718096;text-transform:uppercase;
        letter-spacing:0.8px;margin-bottom:12px;font-family:Arial,sans-serif;">{title}</div>
      <table style="border-collapse:collapse;">
        <tr style="vertical-align:bottom;">{bars}</tr>
      </table>
      <div style="height:1px;background:#edf2f7;margin-top:2px;"></div>
    </div>"""


def get_mls_detail():
    """
    Active / Under Contract / Sold counts per price band, per MLS_DETAIL_CATEGORIES.
    Returns None until the Paragon saved-search email parser exists.

    Blocked on two things, in order:
      1. Saved searches set up in both Black Hills MLS and Mount Rushmore MLS
         (Paragon 5), each set to weekly-email its export to arecblackhills@gmail.com.
      2. An IMAP-based parser here that reads those export emails and returns:
           { category: { band_label: {"Active": n, "Under Contract": n, "Sold": n}, ... }, ... }
         where category is one of MLS_DETAIL_CATEGORIES and band_label matches
         a label in PRICE_BANDS. A sample export email is needed to build the parser
         against Paragon's actual CSV/column format.
    """
    return None


def build_mls_detail_section(mls_detail=None):
    """Renders the price-band x status table for every MLS_DETAIL_CATEGORIES entry.
    Cells show "—" until get_mls_detail() returns real counts."""
    th = ("text-align:left;padding:8px 12px;font-size:10px;color:#a0aec0;"
          "text-transform:uppercase;letter-spacing:0.6px;font-family:Arial,sans-serif;"
          "border-bottom:2px solid #edf2f7;")
    td = ("padding:8px 12px;font-size:12px;color:#2d3748;font-family:Arial,sans-serif;"
          "border-bottom:1px solid #f7fafc;")

    status_cols = "".join(f'<th style="{th}">{s}</th>' for s in MLS_STATUSES)

    category_tables = ""
    for category in MLS_DETAIL_CATEGORIES:
        rows = ""
        for band_label, lo, hi in PRICE_BANDS:
            cells = ""
            for status in MLS_STATUSES:
                val = (mls_detail or {}).get(category, {}).get(band_label, {}).get(status)
                cells += f'<td style="{td}">{val if val is not None else "—"}</td>'
            rows += f'<tr><td style="{td}font-weight:600;color:#1a202c;">{band_label}</td>{cells}</tr>'
        category_tables += f"""
        <div style="margin-bottom:16px;">
          <div style="font-size:12px;font-weight:700;color:#1a202c;margin-bottom:6px;
            font-family:Arial,sans-serif;">{category}</div>
          <table style="width:100%;border-collapse:collapse;">
            <thead><tr><th style="{th}">Price Band</th>{status_cols}</tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>"""

    pending_note = "" if mls_detail else """
      <div style="font-size:11px;color:#b7791f;background:#fffbeb;border:1px solid #f6e05e;
        border-radius:8px;padding:10px 14px;margin-top:2px;font-family:Arial,sans-serif;">
        <strong>Pending:</strong> cells show "—" until Paragon saved searches (Black Hills MLS +
        Mount Rushmore MLS) are set to weekly-export &rarr; arecblackhills@gmail.com, and the
        agent's email parser is built to read them.
      </div>"""

    return f"""
    <div style="margin-bottom:24px;">
      <div style="font-size:10px;font-weight:700;color:#718096;text-transform:uppercase;
        letter-spacing:0.8px;margin-bottom:12px;font-family:Arial,sans-serif;">
        MLS Detail &mdash; Current Week by Price Band
      </div>
      {category_tables}
      {pending_note}
    </div>"""


# ── REPORT BUILDER ───────────────────────────────────────────────────────────

def build_html(rates, city_data, trend_data=None, tier_data=None):
    today = datetime.now().strftime("%B %d, %Y")
    r30   = rates["30yr"]
    r15   = rates["15yr"]

    th = ("text-align:left;padding:9px 14px;font-size:11px;color:#a0aec0;"
          "font-weight:700;text-transform:uppercase;letter-spacing:0.5px;"
          "border-bottom:2px solid #edf2f7;font-family:Arial,sans-serif;")
    td = "padding:11px 14px;color:#2d3748;font-size:13px;font-family:Arial,sans-serif;"

    # ── Rapid City spotlight
    rc = city_data.get("Rapid City", {})

    def inv_badge(d):
        if "inventory_change" not in d:
            return ""
        ic  = d["inventory_change"]
        col = "#38a169" if ic < 0 else "#e53e3e"
        return f' <span style="color:{col};font-size:11px;font-family:Arial,sans-serif;">({ic:+.0f} MoM)</span>'

    def pct_above_fmt(d):
        val = d.get("pct_above")
        if val is None:
            return "N/A"
        try:
            v   = float(val) * 100
            col = "#38a169" if v >= 50 else "#e53e3e"
            return f'<span style="color:{col};font-weight:700;">{v:.0f}%</span>'
        except Exception:
            return "N/A"

    rc_block = f"""
    <div style="background:#f0f7ff;border:1px solid #bee3f8;border-radius:10px;
      padding:20px 24px;margin-bottom:8px;">
      <div style="font-size:11px;font-weight:700;color:#2b6cb0;
        text-transform:uppercase;letter-spacing:0.8px;margin-bottom:14px;
        font-family:Arial,sans-serif;">★ Rapid City — Full Market Snapshot</div>
      <div style="display:flex;gap:24px;flex-wrap:wrap;">
        <div>
          <div style="font-size:10px;color:#718096;text-transform:uppercase;
            letter-spacing:0.5px;margin-bottom:3px;font-family:Arial,sans-serif;">Home Value (ZHVI)</div>
          <div style="font-size:18px;font-weight:800;color:#1a202c;font-family:Arial,sans-serif;">{fc(rc.get('zhvi','N/A'))}</div>
          <div style="font-size:12px;font-family:Arial,sans-serif;">{fpct(rc.get('zhvi_change','N/A'))} MoM</div>
        </div>
        <div>
          <div style="font-size:10px;color:#718096;text-transform:uppercase;
            letter-spacing:0.5px;margin-bottom:3px;font-family:Arial,sans-serif;">Median Sale Price</div>
          <div style="font-size:18px;font-weight:800;color:#1a202c;font-family:Arial,sans-serif;">{fc(rc.get('sale_price','N/A'))}</div>
          <div style="font-size:12px;font-family:Arial,sans-serif;">{fpct(rc.get('sale_price_change','N/A'))} MoM</div>
        </div>
        <div>
          <div style="font-size:10px;color:#718096;text-transform:uppercase;
            letter-spacing:0.5px;margin-bottom:3px;font-family:Arial,sans-serif;">Active Inventory</div>
          <div style="font-size:18px;font-weight:800;color:#1a202c;font-family:Arial,sans-serif;">{fi(rc.get('inventory','N/A'))}</div>
          <div style="font-size:12px;color:#718096;font-family:Arial,sans-serif;">{inv_badge(rc)}</div>
        </div>
        <div>
          <div style="font-size:10px;color:#718096;text-transform:uppercase;
            letter-spacing:0.5px;margin-bottom:3px;font-family:Arial,sans-serif;">New Listings</div>
          <div style="font-size:18px;font-weight:800;color:#1a202c;font-family:Arial,sans-serif;">{fi(rc.get('new_listings','N/A'))}</div>
        </div>
        <div>
          <div style="font-size:10px;color:#718096;text-transform:uppercase;
            letter-spacing:0.5px;margin-bottom:3px;font-family:Arial,sans-serif;">Sold Above List</div>
          <div style="font-size:18px;font-weight:800;color:#1a202c;font-family:Arial,sans-serif;">{pct_above_fmt(rc)}</div>
          <div style="font-size:11px;color:#718096;font-family:Arial,sans-serif;">of homes closed over ask</div>
        </div>
      </div>
    </div>"""

    # ── Trend chart
    chart_html = ""
    if trend_data:
        chart_html = build_bar_chart_html(trend_data[-6:])

    # ── Price tier table
    tier_html = ""
    if tier_data:
        tier_rows = ""
        for label, data in tier_data.items():
            tier_rows += f"""
            <tr style="border-bottom:1px solid #f7fafc;">
              <td style="{td}font-weight:600;">{label}</td>
              <td style="{td}font-weight:800;">{fc(data['value'])}</td>
              <td style="{td}">{fpct(data['change'])} MoM</td>
            </tr>"""

        tier_html = f"""
        <div style="margin-bottom:24px;">
          <div style="font-size:11px;font-weight:700;color:#718096;text-transform:uppercase;
            letter-spacing:0.8px;margin-bottom:10px;font-family:Arial,sans-serif;">
            Home Values by Bedroom Count — Rapid City (Zillow)
          </div>
          <table style="width:100%;border-collapse:collapse;">
            <thead><tr>
              <th style="{th}">Home Size</th>
              <th style="{th}">Typical Value</th>
              <th style="{th}">Month-over-Month</th>
            </tr></thead>
            <tbody>{tier_rows}</tbody>
          </table>
          <div style="font-size:10px;color:#a0aec0;margin-top:8px;font-family:Arial,sans-serif;">
            Bedroom-count ZHVI approximates price bands. Exact $100K–$350K / $350K–$500K / etc. breakdowns
            require Paragon MLS exports → arecblackhills@gmail.com (see setup section below).
          </div>
        </div>"""

    # ── Regional breakdown
    city_rows = ""
    for city, d in city_data.items():
        city_rows += f"""
        <tr style="border-bottom:1px solid #f7fafc;">
          <td style="{td}font-weight:700;color:#1a202c;">{city}</td>
          <td style="{td}">{fc(d.get('zhvi','N/A'))}<br/>
            <span style="font-size:12px;font-family:Arial,sans-serif;">{fpct(d.get('zhvi_change','N/A'))} MoM</span></td>
          <td style="{td}">{fi(d.get('inventory','N/A'))}{inv_badge(d)}</td>
          <td style="{td}">{fi(d.get('new_listings','N/A'))}</td>
        </tr>"""

    # ── MLS detail section (real table shape; cells pending Paragon email parser)
    mls_pending = build_mls_detail_section(get_mls_detail())

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8"/>
  <title>Market Report — {today} — Kevin Andreson</title>
</head>
<body style="margin:0;padding:0;background:#f0f4f8;
  font-family:Arial,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="max-width:720px;margin:0 auto;padding:24px;">

  <!-- HEADER -->
  <div style="background:#0f2942;border-radius:12px 12px 0 0;padding:32px 36px 28px;">
    <div style="color:#7fb3e0;font-size:11px;font-weight:700;
      letter-spacing:1.2px;text-transform:uppercase;margin-bottom:6px;">
      Weekly Market Report
    </div>
    <div style="color:white;font-size:26px;font-weight:800;line-height:1.2;">
      Black Hills Market Update
    </div>
    <div style="color:#90b8d8;font-size:13px;margin-top:8px;">
      {today} &bull; {MARKET_LABEL} &bull; Kevin Andreson, Keller Williams
    </div>
  </div>

  <!-- RATE BAR -->
  <div style="background:#1a3a5c;padding:22px 36px;border-bottom:1px solid #1d5080;">
    <div style="display:flex;gap:48px;flex-wrap:wrap;">
      <div>
        <div style="color:#7fb3e0;font-size:10px;font-weight:700;
          text-transform:uppercase;letter-spacing:0.8px;margin-bottom:5px;">30-Year Fixed</div>
        <div>
          <span style="color:white;font-size:30px;font-weight:800;">{r30['rate']}%</span>
          <span style="font-size:13px;margin-left:10px;">{frate_change(r30['change'])}</span>
        </div>
      </div>
      <div>
        <div style="color:#7fb3e0;font-size:10px;font-weight:700;
          text-transform:uppercase;letter-spacing:0.8px;margin-bottom:5px;">15-Year Fixed</div>
        <div>
          <span style="color:white;font-size:30px;font-weight:800;">{r15['rate']}%</span>
          <span style="font-size:13px;margin-left:10px;">{frate_change(r15['change'])}</span>
        </div>
      </div>
      <div style="margin-left:auto;align-self:flex-end;">
        <div style="color:#4a7fa8;font-size:10px;">Source: Federal Reserve (FRED)</div>
      </div>
    </div>
  </div>

  <!-- MARKET DATA -->
  <div style="background:white;padding:28px 36px;border-top:3px solid #1d7eea;">
    <div style="margin-bottom:6px;">
      <span style="background:#ebf4ff;color:#2b6cb0;font-size:12px;font-weight:700;
        padding:4px 12px;border-radius:6px;font-family:Arial,sans-serif;">ZILLOW RESEARCH</span>
    </div>
    <div style="color:#718096;font-size:12px;margin-bottom:20px;font-family:Arial,sans-serif;">
      Black Hills Region, SD — Rapid City · Spearfish · Sturgis · Hot Springs · Box Elder · Hermosa · Custer · Piedmont
    </div>

    {rc_block}
    {chart_html}
    {tier_html}

    <div style="font-size:11px;font-weight:700;color:#718096;text-transform:uppercase;
      letter-spacing:0.8px;margin-bottom:12px;margin-top:24px;font-family:Arial,sans-serif;">
      Regional Breakdown
    </div>
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr>
        <th style="{th}">City</th>
        <th style="{th}">Home Value (ZHVI)</th>
        <th style="{th}">Active Inventory</th>
        <th style="{th}">New Listings</th>
      </tr></thead>
      <tbody>{city_rows}</tbody>
    </table>
  </div>

  <!-- MLS DETAIL SECTION -->
  <div style="background:white;padding:0 36px 28px;">
    {mls_pending}
  </div>

  <!-- LEGEND -->
  <div style="background:#f7fafc;padding:16px 36px;border-top:1px solid #edf2f7;">
    <div style="font-size:11px;color:#a0aec0;line-height:1.9;font-family:Arial,sans-serif;">
      <strong style="color:#718096;">ZHVI</strong> = Zillow estimated home value &nbsp;&bull;&nbsp;
      <strong style="color:#718096;">Tiers</strong> = lower / mid / upper thirds of the market &nbsp;&bull;&nbsp;
      <strong style="color:#718096;">Sold Above List</strong> = % of homes closed over asking
    </div>
  </div>

  <!-- FOOTER -->
  <div style="background:#f0f4f8;border-radius:0 0 12px 12px;
    padding:18px 36px;text-align:center;border-top:1px solid #e2e8f0;">
    <div style="font-size:11px;color:#a0aec0;line-height:1.8;font-family:Arial,sans-serif;">
      Data: Zillow Research &bull; Federal Reserve FRED<br/>
      Kevin Andreson, Keller Williams &bull; Auto-generated every Monday 6:00 AM
    </div>
  </div>

</div>
</body>
</html>"""


# ── DASHBOARD DATA EXPORT ────────────────────────────────────────────────────

def save_dashboard_js(rates, city_data, trend_data, tier_data):
    """Write js/market-data.js so index.html can display live data."""
    rc = city_data.get("Rapid City", {})

    trend = []
    for d, v in (trend_data[-6:] if trend_data else []):
        try:
            label = datetime.strptime(d[:7], "%Y-%m").strftime("%b '%y")
        except Exception:
            label = d[:7]
        trend.append({"month": label, "value": round(v)})

    tiers = [
        {"label": lbl, "value": round(d["value"]), "change": d["change"]}
        for lbl, d in (tier_data or {}).items()
    ]

    cities = []
    for city, d in city_data.items():
        cities.append({
            "name":            city,
            "zhvi":            round(d["zhvi"]) if d.get("zhvi") else None,
            "zhviChange":      d.get("zhvi_change"),
            "inventory":       round(d["inventory"]) if d.get("inventory") else None,
            "inventoryChange": round(d["inventory_change"]) if d.get("inventory_change") else None,
            "newListings":     round(d["new_listings"]) if d.get("new_listings") else None,
        })

    pct_raw   = rc.get("pct_above")
    pct_above = round(float(pct_raw) * 100) if pct_raw is not None else None

    data = {
        "generated": datetime.now().strftime("%B %d, %Y"),
        "rates": {
            "rate30":   rates["30yr"]["rate"],
            "change30": rates["30yr"]["change"],
            "rate15":   rates["15yr"]["rate"],
            "change15": rates["15yr"]["change"],
        },
        "rapidCity": {
            "zhvi":            round(rc["zhvi"]) if rc.get("zhvi") else None,
            "zhviChange":      rc.get("zhvi_change"),
            "salePrice":       round(rc["sale_price"]) if rc.get("sale_price") else None,
            "salePriceChange": rc.get("sale_price_change"),
            "inventory":       round(rc["inventory"]) if rc.get("inventory") else None,
            "inventoryChange": round(rc["inventory_change"]) if rc.get("inventory_change") else None,
            "newListings":     round(rc["new_listings"]) if rc.get("new_listings") else None,
            "pctAbove":        pct_above,
        },
        "trend":  trend,
        "tiers":  tiers,
        "cities": cities,
        "mlsDetail": {
            "categories": MLS_DETAIL_CATEGORIES,
            "priceBands": [label for label, lo, hi in PRICE_BANDS],
            "statuses":   MLS_STATUSES,
            "data":       get_mls_detail(),  # None until Paragon export parser exists
        },
    }

    with open(DASHBOARD_JS, "w") as f:
        f.write(f"// Auto-generated by mls_report.py — {data['generated']}\n")
        f.write(f"window.MARKET_DATA = {json.dumps(data, indent=2)};\n")
    print(f"      Dashboard data → js/market-data.js")


# ── EMAIL ────────────────────────────────────────────────────────────────────

def send_email(html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Market Report — {datetime.now().strftime('%B %d, %Y')} — Black Hills, SD"
    msg["From"]    = FROM_EMAIL
    msg["To"]      = TO_EMAIL
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(FROM_EMAIL, GMAIL_APP_PASSWORD)
        s.sendmail(FROM_EMAIL, TO_EMAIL, msg.as_string())
    print(f"  Email sent → {TO_EMAIL}")


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    preview_only = "--send" not in sys.argv

    print("\nMarket Report Agent — Kevin Andreson")
    print("=" * 42)

    print("\n[1/5] Fetching mortgage rates from FRED...")
    rates = get_mortgage_rates()
    print(f"      30-yr: {rates['30yr']['rate']}%  |  15-yr: {rates['15yr']['rate']}%")

    print("\n[2/5] Fetching Zillow market data...")
    city_data = get_zillow_data()
    print(f"      Data loaded for: {', '.join(city_data.keys())}")

    print("\n[3/5] Fetching 6-month ZHVI trend...")
    trend_data = get_zhvi_trend("Rapid City", n=7)
    print(f"      {len(trend_data)} months of trend data")

    print("\n[4/5] Fetching price tier data...")
    tier_data = get_zhvi_tiers("Rapid City")
    print(f"      Tiers loaded: {', '.join(tier_data.keys())}")

    print("\n[5/5] Building report and updating dashboard...")
    html = build_html(rates, city_data, trend_data=trend_data, tier_data=tier_data)

    with open(PREVIEW_FILE, "w") as f:
        f.write(html)
    print(f"      Preview saved → {PREVIEW_FILE}")

    save_dashboard_js(rates, city_data, trend_data, tier_data)

    if preview_only:
        print("\n  PREVIEW MODE — email not sent.")
        print("  Open preview_report.html in your browser to review.")
        print("  To send: python3 mls_report.py --send")
    else:
        print("\n  Sending email...")
        send_email(html)

    print("\nDone.\n")


if __name__ == "__main__":
    main()
