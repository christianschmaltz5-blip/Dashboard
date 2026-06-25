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
    rc    = city_data.get("Rapid City", {})

    S = "font-family:Arial,sans-serif;"  # base style shorthand

    def inv_delta(d):
        ic = d.get("inventory_change")
        if ic is None:
            return ""
        col = "#16a34a" if ic < 0 else "#dc2626"
        return f'<span style="color:{col};font-size:11px;{S}"> ({ic:+.0f} MoM)</span>'

    def pct_above_fmt(d):
        val = d.get("pct_above")
        if val is None:
            return "—"
        try:
            v   = float(val) * 100
            col = "#16a34a" if v >= 50 else "#dc2626"
            return f'<span style="color:{col};font-weight:700;">{v:.0f}%</span>'
        except Exception:
            return "—"

    # ── Rapid City stat grid (table-based — works in all email clients)
    def stat_cell(label, value, sub="", border_right=True):
        br = "border-right:1px solid #e2e8f0;" if border_right else ""
        return f"""<td width="33%" valign="top" style="padding:18px 20px;{br}{S}">
          <div style="font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;
            letter-spacing:0.6px;margin-bottom:8px;{S}">{label}</div>
          <div style="font-size:22px;font-weight:800;color:#0f172a;line-height:1;{S}">{value}</div>
          {"" if not sub else f'<div style="font-size:12px;color:#64748b;margin-top:5px;{S}">{sub}</div>'}
        </td>"""

    rc_block = f"""
    <table width="100%" cellpadding="0" cellspacing="0"
      style="border:1px solid #e2e8f0;border-radius:10px;border-collapse:separate;
             border-spacing:0;margin-bottom:24px;overflow:hidden;">
      <tr style="border-bottom:1px solid #e2e8f0;">
        {stat_cell("Home Value (ZHVI)", fc(rc.get("zhvi","—")),
                   f'{fpct(rc.get("zhvi_change",""))} MoM')}
        {stat_cell("Median Sale Price", fc(rc.get("sale_price","—")),
                   f'{fpct(rc.get("sale_price_change",""))} MoM')}
        {stat_cell("Active Inventory", fi(rc.get("inventory","—")),
                   inv_delta(rc), border_right=False)}
      </tr>
      <tr>
        {stat_cell("New Listings", fi(rc.get("new_listings","—")))}
        {stat_cell("Sold Above Asking", pct_above_fmt(rc), "of closings over list price")}
        <td width="33%" style="padding:18px 20px;{S}"></td>
      </tr>
    </table>"""

    # ── Trend chart
    chart_html = ""
    if trend_data:
        chart_html = build_bar_chart_html(trend_data[-6:])

    # ── Price tiers
    tier_html = ""
    if tier_data:
        tier_rows = ""
        for label, data in tier_data.items():
            tier_rows += f"""<tr style="border-bottom:1px solid #f1f5f9;">
              <td style="padding:10px 14px;font-size:13px;font-weight:600;color:#1e293b;{S}">{label}</td>
              <td style="padding:10px 14px;font-size:13px;font-weight:800;color:#0f172a;{S}">{fc(data["value"])}</td>
              <td style="padding:10px 14px;font-size:13px;{S}">{fpct(data["change"])} MoM</td>
            </tr>"""
        tier_html = f"""
        <table width="100%" cellpadding="0" cellspacing="0"
          style="border-collapse:collapse;margin-bottom:28px;">
          <thead><tr style="border-bottom:2px solid #e2e8f0;">
            <th style="text-align:left;padding:8px 14px;font-size:10px;font-weight:700;
              color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;{S}">Home Size</th>
            <th style="text-align:left;padding:8px 14px;font-size:10px;font-weight:700;
              color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;{S}">Typical Value</th>
            <th style="text-align:left;padding:8px 14px;font-size:10px;font-weight:700;
              color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;{S}">Month-over-Month</th>
          </tr></thead>
          <tbody>{tier_rows}</tbody>
        </table>"""

    # ── Regional breakdown
    city_rows = ""
    for city, d in city_data.items():
        zhvi_chg = d.get("zhvi_change")
        chg_html = f'&nbsp;{fpct(zhvi_chg)} MoM' if zhvi_chg is not None else ""
        city_rows += f"""<tr style="border-bottom:1px solid #f1f5f9;">
          <td style="padding:11px 14px;font-size:13px;font-weight:700;color:#0f172a;{S}">{city}</td>
          <td style="padding:11px 14px;font-size:13px;color:#334155;{S}">{fc(d.get("zhvi","—"))}{chg_html}</td>
          <td style="padding:11px 14px;font-size:13px;color:#334155;{S}">{fi(d.get("inventory","—"))}{inv_delta(d)}</td>
          <td style="padding:11px 14px;font-size:13px;color:#334155;{S}">{fi(d.get("new_listings","—"))}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/>
<title>Black Hills Market Report — {today}</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;{S}">
<table width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:24px 16px;">
<table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;">

  <!-- HEADER -->
  <tr><td style="background:#0f172a;border-radius:12px 12px 0 0;padding:32px 36px 26px;">
    <div style="color:#7fb3e0;font-size:10px;font-weight:700;letter-spacing:1.4px;
      text-transform:uppercase;margin-bottom:8px;{S}">Weekly Market Report</div>
    <div style="color:#ffffff;font-size:28px;font-weight:800;line-height:1.15;{S}">
      Black Hills Market Update</div>
    <div style="color:#94a3b8;font-size:13px;margin-top:8px;{S}">
      {today} &nbsp;&bull;&nbsp; {MARKET_LABEL} &nbsp;&bull;&nbsp; Kevin Andreson, Keller Williams
    </div>
  </td></tr>

  <!-- MORTGAGE RATES -->
  <tr><td style="background:#1e3a5f;padding:0;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td width="50%" style="padding:22px 28px 22px 36px;border-right:1px solid #2d4f7c;">
          <div style="color:#7fb3e0;font-size:10px;font-weight:700;text-transform:uppercase;
            letter-spacing:0.8px;margin-bottom:6px;{S}">30-Year Fixed</div>
          <span style="color:#fff;font-size:32px;font-weight:800;{S}">{r30["rate"]}%</span>
          <span style="font-size:13px;margin-left:10px;">{frate_change(r30["change"])}</span>
        </td>
        <td width="50%" style="padding:22px 36px 22px 28px;">
          <div style="color:#7fb3e0;font-size:10px;font-weight:700;text-transform:uppercase;
            letter-spacing:0.8px;margin-bottom:6px;{S}">15-Year Fixed</div>
          <span style="color:#fff;font-size:32px;font-weight:800;{S}">{r15["rate"]}%</span>
          <span style="font-size:13px;margin-left:10px;">{frate_change(r15["change"])}</span>
        </td>
      </tr>
    </table>
  </td></tr>

  <!-- BODY -->
  <tr><td style="background:#ffffff;padding:32px 36px;border-left:1px solid #e2e8f0;
    border-right:1px solid #e2e8f0;">

    <!-- Section label -->
    <div style="font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;
      letter-spacing:1px;margin-bottom:18px;{S}">Rapid City — Full Snapshot</div>

    {rc_block}
    {chart_html}

    {"" if not tier_data else f'''
    <div style="font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;
      letter-spacing:1px;margin-bottom:14px;{S}">Value by Bedroom Count</div>
    {tier_html}'''}

    <!-- Regional -->
    <div style="font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;
      letter-spacing:1px;margin-bottom:14px;margin-top:8px;{S}">Regional Breakdown</div>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      <thead><tr style="border-bottom:2px solid #e2e8f0;">
        <th style="text-align:left;padding:8px 14px;font-size:10px;font-weight:700;
          color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;{S}">City</th>
        <th style="text-align:left;padding:8px 14px;font-size:10px;font-weight:700;
          color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;{S}">Home Value</th>
        <th style="text-align:left;padding:8px 14px;font-size:10px;font-weight:700;
          color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;{S}">Inventory</th>
        <th style="text-align:left;padding:8px 14px;font-size:10px;font-weight:700;
          color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;{S}">New Listings</th>
      </tr></thead>
      <tbody>{city_rows}</tbody>
    </table>

  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:#f8fafc;border:1px solid #e2e8f0;border-top:none;
    border-radius:0 0 12px 12px;padding:16px 36px;text-align:center;">
    <div style="font-size:11px;color:#94a3b8;line-height:1.8;{S}">
      Data: Zillow Research &nbsp;&bull;&nbsp; Federal Reserve FRED<br/>
      ZHVI = Zillow estimated home value &nbsp;&bull;&nbsp; Sold Above List = % of homes closed over asking<br/>
      Auto-generated every Monday 6:00 AM
    </div>
  </td></tr>

</table>
</td></tr>
</table>
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

def send_email(html, subject):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
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

    rc = city_data.get("Rapid City", {})
    zhvi_chg = rc.get("zhvi_change") or 0
    sign = "+" if zhvi_chg > 0 else ""
    r30  = rates["30yr"]["rate"]
    subject = (
        f"Black Hills Market · 30yr at {r30}% · "
        f"Rapid City {sign}{zhvi_chg:.1f}% · {datetime.now().strftime('%b %d')}"
    )

    if preview_only:
        print(f"\n  PREVIEW MODE — email not sent.")
        print(f"  Subject would be: {subject}")
        print("  Open preview_report.html in your browser to review.")
        print("  To send: python3 mls_report.py --send")
    else:
        print(f"\n  Sending email...")
        print(f"  Subject: {subject}")
        send_email(html, subject)

    print("\nDone.\n")


if __name__ == "__main__":
    main()
