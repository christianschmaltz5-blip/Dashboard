// listings-data.js — real Black Hills listings for the KW Black Hills listings site.
//
// Reconciliation note: ~/arc-dashboard/pages/hwy1416-box-elder.html is Kevin Andreson's
// internal newsletter/campaign dashboard for the "Highway 1416, Box Elder" property — it is
// NOT a distinct parcel. Its own marketing templates (templates/hwy1416-executive.html,
// hwy1416-modern.html) and the linked Master Plan template (templates/hwy1416-masterplan.html)
// describe the Highway 1416 address as the site of the Freedom Estates development, and the
// masterplan template explicitly breaks it into "Two shovel-ready tracts": a 24.76-acre
// Multi-Family tract ($3,750,000, Freedom Tracts Subdivision) and a 7.30-acre Light
// Industrial / Commercial tract ($1,150,000) — matching the verified Freedom Estates figures
// exactly. So Highway 1416 = the Freedom Estates tracts, represented once each below, not a
// third listing. Zoning (C-2) and highway-frontage/AFB-distance figures below come from the
// hwy1416-executive.html and hwy1416-modern.html templates, the most detailed source for the
// Multi-Family tract; no equivalent zoning detail exists for the Light Industrial tract, so
// that field is left null rather than assumed.
//
// Image note: the only real Freedom Estates photo/map assets on disk live directly in
// ~/arc-dashboard/pages/ (freedom-estates-thumb.jpg, freedom-estates-map.jpg) — there is no
// img/ copy of them. Since this site lives at pages/listings.html, they're same-directory
// paths, not "../img/...".
window.LISTINGS = [
  {
    id: "freedom-estates-multifamily",
    title: "Freedom Estates — Multi-Family Tract",
    type: "Land · Multi-Family",
    status: "Available",
    price: 3750000,
    priceDisplay: "$3,750,000",
    acreage: 24.76,
    city: "Box Elder", state: "SD",
    location: "Highway 1416 · I-90 Exit 67 · adjacent Ellsworth AFB",
    summary: "Shovel-ready, graded, permitted, and utility-served multi-family tract in the Freedom Tracts Subdivision along Highway 1416 — about 1.8 miles from the Ellsworth AFB main gate at I-90 Exit 67, within the Liberty Blvd commercial corridor and near the future Douglas High School.",
    highlights: [
      "24.76 acres",
      "C-2 zoned — no rezoning or annexation contingency",
      "Graded, permitted & utility-served",
      "~1,200 linear feet of highway frontage",
      "~1.8 miles from Ellsworth AFB main gate",
      "I-90 Exit 67",
      "Adjacent Ellsworth AFB / future home of the B-21 Raider"
    ],
    details: {
      zoning: "C-2",
      utilities: "All utilities on site",
      access: "I-90 Exit 67",
      subdivision: "Freedom Tracts Subdivision"
    },
    image: "freedom-estates-thumb.jpg",
    featured: true
  },
  {
    id: "freedom-estates-light-industrial",
    title: "Freedom Estates — Light Industrial / Commercial Tract",
    type: "Land · Light Industrial / Commercial",
    status: "Available",
    price: 1150000,
    priceDisplay: "$1,150,000",
    acreage: 7.30,
    city: "Box Elder", state: "SD",
    location: "Liberty Boulevard corridor · Box Elder, SD",
    summary: "Flat, graded commercial parcel with I-90 visibility near Liberty Boulevard, fronting a corridor carrying 34,600+ vehicles per day — part of the Freedom Estates development, adjacent to the Multi-Family tract.",
    highlights: [
      "7.30 acres",
      "Graded & flat",
      "I-90 visibility",
      "Fronts a corridor carrying 34,600+ vehicles/day",
      "Adjacent to the Freedom Estates Multi-Family tract"
    ],
    details: {
      zoning: null,
      utilities: null,
      access: "Liberty Boulevard / I-90 corridor",
      subdivision: null
    },
    image: "freedom-estates-map.jpg",
    featured: false
  }
];
