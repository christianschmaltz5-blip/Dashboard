#!/usr/bin/env python3
"""
Parcel → Owner lookup (Phase 1 of the skip-trace agent) — Kevin Andreson / KW Black Hills

Type in an address (or parcel ID) and get the parcel's owner of record — usually
the LLC / trust that holds it — plus the owner's mailing address, acreage, zoning
land-use, and assessed value. This is the foundation for skip tracing: once you
have the owning entity + mailing address, Phase 2 (SD Secretary of State) finds the
humans behind an LLC, and Phase 3 (a licensed skip-trace API) finds their contacts.

Covers the two Black Hills counties that matter:
  • Meade County   (Box Elder, Summerset, Piedmont, Sturgis, Ellsworth AFB corridor)
      — has a real situs ADDRESS field, so address lookups are exact, no geocoding.
  • Pennington County (Rapid City + rural)
      — no situs field, so address lookups geocode the address then find the parcel
        polygon that contains that point.

Usage:
  python3 parcel_lookup.py "11160 Liberty St, Summerset SD"
  python3 parcel_lookup.py "0125400002"           # by parcel ID
  python3 parcel_lookup.py --json "123 Main St, Box Elder SD"

Programmatic:
  from parcel_lookup import lookup
  rec = lookup("11160 Liberty St, Summerset SD")   # -> dict or None

All data sources are free public records. No API keys required for Phase 1.
"""

import argparse
import json
import re
import sys
import requests
from urllib.parse import urlencode

HEADERS = {"User-Agent": "KW Black Hills Parcel Lookup (Kevin Andreson)"}
TIMEOUT = 25

# ── County parcel layers (verified live 2026-07-06) ──────────────────────────
MEADE = {
    "name": "Meade",
    "url": "https://gis.rcgov.org/server/rest/services/AGOL/MPO/MapServer/0/query",
    "situs_field": "ADDRESS",          # Meade publishes situs addresses — exact lookup
    "fields": {
        "parcel_id": "PARCELID",
        "owner": "DEEDHOLD",
        "owner2": "deedaddr1",         # co-owner / c-o line
        "mail_street": "deedaddr2",
        "mail_citystate": "deedaddr3",
        "mail_zip": "deedzip",
        "situs": "ADDRESS",
        "place": "str",
        "acres": "GrossAcres",
        "legal": "LegalDesc",
        "value": "AssdValue",
        "landuse": None,
    },
}
PENNINGTON = {
    "name": "Pennington",
    "url": "https://services1.arcgis.com/AhXvNWFdL7hH4TjJ/ArcGIS/rest/services/PenningtonParcels/FeatureServer/0/query",
    "situs_field": None,               # no situs field — geocode + point-in-parcel
    "fields": {
        "parcel_id": "PIN",
        "owner": "GranteeLas",
        "owner2": None,
        "mail_street": "GranteeFul",
        "mail_citystate": None,        # city/state/zip are separate
        "mail_city": "GranteeCit",
        "mail_state": "GranteeSta",
        "mail_zip": "GranteeZip",
        "situs": None,
        "place": "Subdivisio",
        "acres": "Acres",
        "legal": "LegalDescr",
        "value": "ValueTotal",
        "landuse": "LandUse",
    },
}
COUNTIES = [MEADE, PENNINGTON]

# Towns that live in Meade County — used to prefer the exact-address path.
MEADE_TOWNS = ("BOX ELDER", "SUMMERSET", "PIEDMONT", "STURGIS", "BLACK HAWK",
               "WHITEWOOD", "ELLSWORTH", "ENNING", "FAITH", "HEREFORD")

ENTITY_MARKERS = (" LLC", " L L C", " LLLP", " LLP", " LP", " INC", " CORP",
                  " CO ", " COMPANY", " TRUST", " TR ", " HOLDINGS", " PARTNERS",
                  " PROPERTIES", " ENTERPRISES", " GROUP", " INVESTMENTS", " FUND",
                  " ASSOCIATES", " VENTURES", " REALTY", " FARMS", " RANCH")


# ── Geocoding (free, no key) ─────────────────────────────────────────────────
def geocode(address):
    """Return (lon, lat) via ArcGIS World Geocoder, falling back to US Census."""
    try:
        r = requests.get(
            "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates",
            params={"SingleLine": address, "maxLocations": 1, "f": "json"},
            headers=HEADERS, timeout=TIMEOUT)
        cand = r.json().get("candidates", [])
        if cand:
            loc = cand[0]["location"]
            return loc["x"], loc["y"]
    except Exception:
        pass
    try:
        r = requests.get(
            "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
            params={"address": address, "benchmark": "Public_AR_Current", "format": "json"},
            headers=HEADERS, timeout=TIMEOUT)
        m = r.json()["result"]["addressMatches"]
        if m:
            c = m[0]["coordinates"]
            return c["x"], c["y"]
    except Exception:
        pass
    return None


# ── ArcGIS query helpers ─────────────────────────────────────────────────────
def _get(url, params):
    r = requests.get(f"{url}?{urlencode(params)}", headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _query_where(county, where):
    j = _get(county["url"], {
        "where": where, "outFields": "*", "returnGeometry": "false", "f": "json"})
    return [f["attributes"] for f in j.get("features", [])]


def _query_point(county, lon, lat, buffers=(0, 60, 200)):
    """Point-in-parcel query, escalating the search buffer to absorb geocode error."""
    for dist in buffers:
        params = {
            "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint",
            "inSR": "4326", "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*", "returnGeometry": "false", "f": "json"}
        if dist:
            params.update({"distance": dist, "units": "esriSRUnit_Foot"})
        feats = _get(county["url"], params).get("features", [])
        if feats:
            return [f["attributes"] for f in feats]
    return []


# ── Normalization ────────────────────────────────────────────────────────────
def _is_entity(name):
    if not name:
        return False
    padded = f" {name.upper()} "
    return any(m in padded for m in ENTITY_MARKERS)


def _normalize(county, attrs):
    f = county["fields"]

    def g(key):
        col = f.get(key)
        return attrs.get(col) if col else None

    # Build a single mailing-address string from whatever fields the county exposes.
    if county is PENNINGTON:
        mail = " ".join(str(x) for x in [
            g("mail_street"),
            ", ".join(str(x) for x in [attrs.get("GranteeCit"), attrs.get("GranteeSta"), attrs.get("GranteeZip")] if x)
        ] if x)
    else:
        mail = " ".join(str(x) for x in [
            g("mail_street"),
            g("mail_citystate"),
            g("mail_zip")] if x)

    owner = (g("owner") or "").strip()
    return {
        "county": county["name"],
        "parcel_id": g("parcel_id"),
        "owner": owner,
        "owner_secondary": (g("owner2") or "").strip() or None,
        "owner_is_entity": _is_entity(owner),
        "mailing_address": re.sub(r"\s+", " ", mail).strip(" ,") or None,
        "situs_address": (g("situs") or "").strip() or None,
        "place": (g("place") or "").strip() or None,
        "acres": g("acres"),
        "legal": (g("legal") or "").strip() or None,
        "assessed_value": g("value"),
        "land_use": (g("landuse") or "").strip() or None,
    }


# ── Public lookup ────────────────────────────────────────────────────────────
def _street_part(address):
    """Strip trailing ', City ST ZIP' so we can match the county situs field."""
    return re.split(r",", address)[0].strip().upper()


def lookup(query):
    """Address or parcel-id -> normalized parcel dict (or None if nothing found)."""
    q = query.strip()

    # Parcel ID (mostly digits, or Meade's dotted form like 0D.75.31D)
    normalized = q.replace("-", "").replace(" ", "")
    if normalized.isdigit() and 6 <= len(normalized) <= 16:
        for county in COUNTIES:
            pid = county["fields"]["parcel_id"]
            rows = _query_where(county, f"{pid} = '{normalized}'")
            if rows:
                return _normalize(county, rows[0])
        return None
    if re.fullmatch(r"[0-9A-Za-z.]+", q) and "." in q:  # Meade dotted parcel id
        rows = _query_where(MEADE, f"PARCELID = '{q.upper()}'")
        if rows:
            return _normalize(MEADE, rows[0])

    # Address path. 1) Meade exact situs match (fast, no geocode).
    street = _street_part(q).replace("'", "''")
    rows = _query_where(MEADE, f"UPPER(ADDRESS) LIKE '%{street}%'")
    if rows:
        return _normalize(MEADE, rows[0])

    # 2) Geocode, then find the containing parcel in either county.
    pt = geocode(q)
    if not pt:
        return None
    lon, lat = pt
    # Prefer Meade if the address names a Meade town, else try Pennington first.
    order = [MEADE, PENNINGTON] if any(t in q.upper() for t in MEADE_TOWNS) else [PENNINGTON, MEADE]
    for county in order:
        rows = _query_point(county, lon, lat)
        if rows:
            return _normalize(county, rows[0])
    return None


# ── Formatting / CLI ─────────────────────────────────────────────────────────
def format_record(rec):
    if not rec:
        return "No parcel found. Try the full street address with city, or the parcel ID."
    tag = "  ⟵ entity (LLC/trust) — run Phase 2 (SD SoS) for the people" if rec["owner_is_entity"] else ""
    lines = [
        f"OWNER      : {rec['owner']}{tag}",
    ]
    if rec["owner_secondary"]:
        lines.append(f"             {rec['owner_secondary']}")
    lines += [
        f"MAILING    : {rec['mailing_address'] or '—'}",
        f"PARCEL     : {rec['parcel_id']}  ({rec['county']} County)",
        f"SITUS      : {rec['situs_address'] or '—'}" + (f"   [{rec['place']}]" if rec['place'] else ""),
        f"ACRES      : {rec['acres'] if rec['acres'] not in (None, 0) else '—'}",
        f"ASSESSED   : ${rec['assessed_value']:,}" if isinstance(rec['assessed_value'], (int, float)) and rec['assessed_value'] else "ASSESSED   : —",
        f"LAND USE   : {rec['land_use'] or '—'}",
        f"LEGAL      : {rec['legal'] or '—'}",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Address/parcel -> owner lookup (Meade + Pennington counties)")
    ap.add_argument("query", nargs="+", help="street address or parcel ID")
    ap.add_argument("--json", action="store_true", help="output raw JSON")
    args = ap.parse_args()
    q = " ".join(args.query)

    try:
        rec = lookup(q)
    except requests.exceptions.RequestException as e:
        print(f"Lookup failed (network/GIS error): {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(rec, indent=2))
    else:
        print(f"\nParcel lookup: {q}\n{'-'*60}")
        print(format_record(rec))


if __name__ == "__main__":
    main()
