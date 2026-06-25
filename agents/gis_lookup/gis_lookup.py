"""
Pennington County GIS Parcel Lookup — Kevin Andreson
Queries the Pennington County ArcGIS REST API for on-demand parcel data:
zoning, ownership, acreage, and utility access.

Usage:
  python3 gis_lookup.py <parcel-id-or-address>

Examples:
  python3 gis_lookup.py "7700031800"           # by APN / parcel ID
  python3 gis_lookup.py "123 Main St"          # by street address (partial OK)

Output: plain-text summary to stdout. If called from another agent,
import and call lookup(query) directly — it returns a dict.

─── SETUP NOTE ──────────────────────────────────────────────────────────────
Pennington County's ArcGIS REST endpoint is set in GIS_BASE_URL below.
To verify the URL is current:
  1. Go to https://pennco.org and search "GIS" or look under County Services.
  2. Open the ArcGIS REST Services Directory at that server.
  3. Find the Parcels layer (usually under "Assessor" or "Parcels" service).
  4. Copy the layer's Query URL and update GIS_BASE_URL below.

The default URL below was correct as of June 2026. If queries return errors,
the endpoint has moved — update GIS_BASE_URL.
─────────────────────────────────────────────────────────────────────────────
"""

import json
import sys
import requests
from urllib.parse import urljoin, urlencode

# ── Configuration ─────────────────────────────────────────────────────────────

# Pennington County ArcGIS parcel layer (assessor/parcel data).
# Update this if the county moves their GIS server.
GIS_BASE_URL = "https://gis.pennco.org/arcgis/rest/services/Parcels/MapServer/0/query"

# Fallback: South Dakota statewide parcel service (GeoJSON parcels layer)
SD_STATE_GIS_URL = "https://sdgis.sd.gov/arcgis/rest/services/SD_All/MapServer/0/query"

HEADERS = {"User-Agent": "Mozilla/5.0 (ARC Parcel Lookup — Kevin Andreson)"}

# Fields to request from the parcel layer.
# Standard Pennington County ArcGIS field names — adjust if their schema differs.
PARCEL_FIELDS = ",".join([
    "PARCEL_ID",     # APN / parcel number
    "OWNER_NAME",    # owner of record
    "SITE_ADDR",     # situs address
    "SITE_CITY",
    "ACRES",         # parcel acreage
    "ZONING",        # zoning code
    "ZONE_DESC",     # zoning description
    "LAND_USE",      # land use classification
    "LEGAL_DESC",    # legal description / subdivision name
    "SCHOOL_DIST",
    "WATER",         # water service provider / availability
    "SEWER",         # sewer service provider / availability
    "ELECTRIC",      # electric utility
])


# ── Core lookup functions ─────────────────────────────────────────────────────

def _query(where_clause, base_url=GIS_BASE_URL):
    """Run a WHERE query against the ArcGIS feature layer and return raw JSON."""
    params = {
        "where": where_clause,
        "outFields": PARCEL_FIELDS,
        "returnGeometry": "false",
        "f": "json",
    }
    url = f"{base_url}?{urlencode(params)}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


def _parse_features(result_json):
    """Extract a list of attribute dicts from an ArcGIS JSON response."""
    features = result_json.get("features", [])
    return [f.get("attributes", {}) for f in features]


def lookup_by_parcel_id(parcel_id):
    """Look up a single parcel by its APN / parcel ID (exact or LIKE match)."""
    clean = parcel_id.strip().replace("-", "").replace(" ", "")
    # Try exact match first, then wildcard
    for clause in [f"PARCEL_ID = '{clean}'", f"PARCEL_ID LIKE '%{clean}%'"]:
        result = _query(clause)
        parcels = _parse_features(result)
        if parcels:
            return parcels
    return []


def lookup_by_address(address):
    """Look up parcels matching a street address (case-insensitive LIKE)."""
    safe = address.strip().replace("'", "''").upper()
    result = _query(f"UPPER(SITE_ADDR) LIKE '%{safe}%'")
    return _parse_features(result)


def lookup(query):
    """
    Auto-detect query type (parcel ID vs address) and return matching parcels.
    Returns a list of attribute dicts (empty list = nothing found).
    """
    # Parcel IDs are typically all-numeric (10–14 digits) possibly with dashes
    normalized = query.strip().replace("-", "").replace(" ", "")
    if normalized.isdigit() and 6 <= len(normalized) <= 16:
        return lookup_by_parcel_id(query)
    return lookup_by_address(query)


# ── Formatting ────────────────────────────────────────────────────────────────

def _fmt(val):
    if val is None or val == "" or val == "N/A":
        return "—"
    if isinstance(val, float):
        return f"{val:,.2f}"
    return str(val)


def format_parcel(attrs):
    """Return a readable text block for one parcel."""
    lines = [
        f"Parcel ID   : {_fmt(attrs.get('PARCEL_ID'))}",
        f"Address     : {_fmt(attrs.get('SITE_ADDR'))}, {_fmt(attrs.get('SITE_CITY'))}",
        f"Owner       : {_fmt(attrs.get('OWNER_NAME'))}",
        f"Acreage     : {_fmt(attrs.get('ACRES'))} ac",
        f"Zoning      : {_fmt(attrs.get('ZONING'))}  —  {_fmt(attrs.get('ZONE_DESC'))}",
        f"Land Use    : {_fmt(attrs.get('LAND_USE'))}",
        f"Legal Desc  : {_fmt(attrs.get('LEGAL_DESC'))}",
        f"School Dist : {_fmt(attrs.get('SCHOOL_DIST'))}",
        "",
        "Utilities",
        f"  Water   : {_fmt(attrs.get('WATER'))}",
        f"  Sewer   : {_fmt(attrs.get('SEWER'))}",
        f"  Electric: {_fmt(attrs.get('ELECTRIC'))}",
    ]
    return "\n".join(lines)


def format_results(parcels, query):
    if not parcels:
        return f'No parcels found for: "{query}"\n\nIf the parcel exists, try:\n  • A shorter portion of the address\n  • The full numeric parcel ID from the county assessor\n  • Checking that GIS_BASE_URL in gis_lookup.py is current'
    out = [f"{len(parcels)} parcel(s) found for: \"{query}\""]
    for i, p in enumerate(parcels, 1):
        out.append(f"\n{'─'*48}")
        if len(parcels) > 1:
            out.append(f"Parcel {i} of {len(parcels)}")
        out.append(format_parcel(p))
    return "\n".join(out)


# ── CLI entrypoint ────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("Usage: python3 gis_lookup.py <parcel-id-or-address>")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    print(f"\nPennington County GIS Lookup: {query}\n")

    try:
        parcels = lookup(query)
    except requests.exceptions.ConnectionError:
        print(
            "Connection failed. Check that GIS_BASE_URL in gis_lookup.py is correct.\n"
            f"  Current URL: {GIS_BASE_URL}\n"
            "  To find the right URL: go to pennco.org → GIS → open the ArcGIS Services Directory."
        )
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"HTTP error from GIS server: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Lookup error: {e}")
        sys.exit(1)

    print(format_results(parcels, query))


if __name__ == "__main__":
    main()
