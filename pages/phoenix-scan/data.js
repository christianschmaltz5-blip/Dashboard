// Phoenix Cap-Rate Watch — scan data
//
// This is the ONLY file the weekly scan updater should touch. Structure:
//
// window.PHX_SCAN = {
//   updated: "YYYY-MM-DD",              // date of the most recent scan
//   listingsScanned: <int>,             // how many listings were reviewed this pass
//   benchmarks: { "<class>": <cap%> },  // class -> benchmark going-in cap rate;
//                                       // a deal "qualifies" at benchmark + 1.00 (100bps)
//   qualifying: [{                      // deals that cleared benchmark + 100bps
//     name, address, zip, ask, units, cls, noi, capPct, spreadBps, confidence, notes, url
//   }],
//   nearMisses: [ /* same shape as qualifying — 50-99bps or unverifiable spread */ ],
//   disqualified: [{                    // broker-stated cap vs re-underwritten reality
//     address, statedCapPct, realCapPct, reason
//   }],
//   history: [{ date, scanned, qualifyingCount, top }]   // one row per past scan run
// };

window.PHX_SCAN = {
  updated: "2026-07-16",
  listingsScanned: 110,
  benchmarks: { "A": 4.75, "B": 4.90, "C": 5.40, "2-4 unit": 5.50 },

  qualifying: [
    {
      name: "Ocotillo Apartments",
      address: "1780 W Missouri Ave",
      zip: "85015",
      ask: 22125000,
      units: 173,
      cls: "C",
      noi: 1604205,
      capPct: 7.25,
      spreadBps: 185,
      confidence: "MEDIUM",
      notes: "118 of 173 units (68%) are rent-restricted under a 25-year HOME Investment Partnership Program obligation dating to 2014 (runs to ~2039). Marketed as part of a 3-property portfolio alongside the Ocotillo Hotel Conversion and Oasis on Grand — whether it can be purchased standalone is unconfirmed. Real dollar NOI disclosed ($1,604,205), which is more credible than a stated-cap-only listing. Verify: standalone-sale terms, actual trailing rent roll.",
      url: "https://www.crexi.com/properties/247054/arizona-ocotillo"
    },
    {
      name: "East Fillmore",
      address: "3044 E Fillmore St",
      zip: "85008",
      ask: 6850000,
      units: 41,
      cls: "C",
      noi: null,
      capPct: 6.84,
      spreadBps: 144,
      confidence: "LOW-MEDIUM",
      notes: "156 days on market (active, last updated 31 days ago). No dollar NOI disclosed — only the stated cap rate — so the expense-ratio sanity check could not be run. Verify: request OM for actual trailing rents/expenses before treating this as real.",
      url: "https://www.crexi.com/properties/2348662/arizona-east-fillmore"
    }
  ],

  nearMisses: [
    {
      name: "Campo Bello Apartments",
      address: "17444 N 32nd St",
      zip: "85032",
      ask: 4995000,
      units: 12,
      cls: "A",
      noi: null,
      capPct: 5.77,
      spreadBps: 102,
      confidence: "LOW",
      notes: "Built 2022, 100% leased. Qualifies on paper but no NOI/rent disclosed to sanity-check — price was consistent across two independent live page loads. Treat as a broker-call lead, not a confirmed deal.",
      url: ""
    }
  ],

  disqualified: [
    {
      address: "2719 W Maryland Ave, Phoenix AZ 85017",
      statedCapPct: 7.82,
      realCapPct: 5.1,
      reason: "8 units, built 1958, renovated 2025-2026, 100% occupied. Stated NOI $108,345 on $127,128 gross implies only ~15% opex — unrealistic for an 8-unit Phoenix property. Re-underwritten at 5% vacancy / 42% opex: NOI ≈ $70,000, real cap ≈5.1% — below the 5.40% Class C benchmark, not above it."
    },
    {
      address: "1017-1031 E Fairmount Ave, Phoenix AZ 85014",
      statedCapPct: 6.50,
      realCapPct: 4.1,
      reason: "8 units, built 1966, renovated 2021, 100% occupied. Stated NOI $126,680 on $146,688 gross implies ~14% opex. Re-underwritten at 5% vacancy / 42% opex: NOI ≈ $80,825, real cap ≈4.1% — well below benchmark."
    },
    {
      address: "3139 N 40th St, Phoenix AZ 85018 (\"Rare Arcadia Multi Family Opportunity\")",
      statedCapPct: 9.37,
      realCapPct: null,
      reason: "5 units, Class B. Listing's own marketing copy describes sober-living/residential-assisted-living use averaging $28,000/month (>$5,000/unit/month) — specialty board-and-care income, not conventional apartment rent. Excluded as non-comparable; the \"spread\" would be measuring the wrong asset class, not a mispricing."
    }
  ],

  history: [
    { date: "2026-07-16", scanned: 110, qualifyingCount: 2, top: "Ocotillo +185bps" }
  ]
};
