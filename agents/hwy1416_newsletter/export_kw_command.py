#!/usr/bin/env python3
"""
Export Highway 1416 prospect list as a KW Command–compatible CSV.
Import this into KW Command: Contacts → Import → CSV
Tag applied: Highway-1416-Prospect
"""
import csv, io, re, os

# ── Recipient list (edit config.py to update) ────────────────────────────────
from config import RECIPIENTS

# ── Best-effort name/company extraction from known emails ────────────────────
KNOWN = {
    "chris@ernstcapitalgroup.com":   ("Chris", "",         "Ernst Capital Group"),
    "ljessen@lloydcompanies.com":    ("L.",    "Jessen",   "Lloyd Companies"),
    "admin@lloydcompanies.com":      ("",      "",         "Lloyd Companies"),
    "bmogen@costelloco.com":         ("B.",    "Mogen",    "Costello Co"),
    "scott@vantiscommercial.com":    ("Scott", "",         "Vantis Commercial"),
    "alex@benderco.com":             ("Alex",  "",         "Bender Co"),
    "info@elevaterapidcity.com":     ("",      "",         "Elevate Rapid City"),
    "info@northpointkc.com":         ("",      "",         "North Point KC"),
    "rthimjon@gmail.com":            ("R.",    "Thimjon",  ""),
    "tmorris@ramkota.com":           ("T.",    "Morris",   "Ramkota"),
    "jquello@aol.com":               ("J.",    "Quello",   ""),
    "jbender@dehs.com":              ("J.",    "Bender",   "DEHS"),
    "sean@bearizona.com":            ("Sean",  "",         "Bear Izona"),
    "justincutler@racpack.com":      ("Justin","Cutler",   "RAC Pack"),
    "bhrebroker@gmail.com":          ("",      "",         "BHR E Broker"),
    "james@clickrain.com":           ("James", "",         "Click Rain"),
    "trebi620@outlook.com":          ("T.",    "Rebi",     ""),
    "wadel@rapidnet.com":            ("W.",    "Adel",     "RapidNet"),
    "jackl@bhcbank.com":             ("Jack",  "L.",       "BHC Bank"),
    "bklynass@rushmore.com":         ("",      "",         "Rushmore"),
    "carey.miller@woodsfuller.com":  ("Carey", "Miller",   "Woods Fuller"),
    "miller.rw@icloud.com":          ("R.W.",  "Miller",   ""),
    "rmuth@muthelectric.com":        ("R.",    "Muth",     "Muth Electric"),
    "rossm@carstarsd.com":           ("Ross",  "M.",       "CARSTAR SD"),
    "sjmcgee6@gmail.com":            ("S.J.",  "McGee",    ""),
    "vnewman31@yahoo.com":           ("V.",    "Newman",   ""),
    "tprendergast@dehs.com":         ("T.",    "Prendergast","DEHS"),
    "ascull@scullconst.com":         ("A.",    "Scull",    "Scull Construction"),
    "joelporch5@gmail.com":          ("Joel",  "Porch",    ""),
    "jschmaltz@ramkota.com":         ("J.",    "Schmaltz", "Ramkota"),
    "greg@sandswellsystems.com":     ("Greg",  "",         "Sands Well Systems"),
    "wicklund.pauljan@gmail.com":    ("Paul Jan","Wicklund",""),
}

TAG = "Highway-1416-Prospect"

rows = []
for email in RECIPIENTS:
    first, last, company = KNOWN.get(email, ("", "", ""))
    rows.append({
        "First Name":   first,
        "Last Name":    last,
        "Email":        email,
        "Company":      company,
        "Phone":        "",
        "Tags":         TAG,
        "Lead Source":  "Highway 1416 Campaign",
        "Notes":        "Commercial land prospect — Highway 1416, Box Elder SD",
    })

out_path = "kw_command_import.csv"
fields = ["First Name","Last Name","Email","Company","Phone","Tags","Lead Source","Notes"]
with open(out_path, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

print(f"Exported {len(rows)} contacts → {out_path}")
print(f"Tag applied: {TAG}")
print(f"Import in KW Command: Contacts → Import → CSV")
