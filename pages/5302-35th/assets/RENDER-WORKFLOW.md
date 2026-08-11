# 5302 N 35th Ave — Image Generation Workflow

## OUTPUT REQUIREMENTS (read this before generating anything)
- Every image must be exported/downloaded individually at native resolution
  — never a flattened grid/contact-sheet/comparison image. If the tool tiles
  multiple scenes into one image, ask it to output each scene as its own
  standalone image in a separate turn, then download each directly (click
  the image itself), not a screenshot of the chat.
- Target 2048px or larger on the long edge — use the tool's HD/upscale
  option if it has one. hero-existing.jpg, build-finished.jpg, and
  gallery-front.jpg matter most (they render largest on the page, close to
  the site's ~1920×1080 hero); the small journey-strip thumbnails tolerate
  lower resolution better since they display tiny on screen.
- Source resolution is the ceiling — cropping or upscaling after the fact
  cannot recover detail that wasn't in the original export.

## MASTER REFERENCE IMAGE
Once build-finished.jpg is approved, it becomes the permanent master
reference. Every gallery image (gallery-front, gallery-corner,
gallery-courtyard, gallery-pool, gallery-lobby, gallery-parking,
gallery-aerial, gallery-night) must use build-finished.jpg as its source —
never an earlier construction stage, never a fresh regeneration.

Permanently locked once build-finished.jpg is approved:
- Building footprint
- Rooflines
- Window spacing
- Balcony locations
- Courtyard dimensions
- Pool dimensions
- Parking layout
- Building height
- Materials
- Landscaping

CRITICAL RULE: every image is an edit of the previous image, never a fresh
generation. The previous output becomes the base for the next prompt.
Building footprint, proportions, architecture, window placement, balconies,
rooflines, landscaping, and camera position must stay identical throughout —
only construction progress or camera angle changes between renders.

## Site constraints
5302 N 35th Ave, Phoenix, AZ 85017 — 0.75 acres, urban infill. Preserve
surrounding houses, the GCU parking garage, road geometry, sidewalks,
utility poles, and lot boundaries. Only replace the development parcel.

## Building spec (locked — paste into every prompt)
30–32 apartment units, three stories, ONE single rectangular or simple
L-shaped building — not a multi-building complex, not multiple wings.
Footprint no larger than roughly 130ft x 60ft. Surface parking only (no
pool, no resort courtyard — those don't fit alongside a 32-unit building
and required parking on 0.75 acres). A small landscaped entry strip is
fine; no large central courtyard. Modern Spanish/Mediterranean
architecture, white smooth stucco, limestone accents, terracotta roof
tiles, black aluminum windows, black metal balconies, warm architectural
lighting, native Arizona landscaping. Never redesign the building once
established.

**Density guardrail (append to every prompt):** "This is a SINGLE
three-story apartment building with exactly 30-32 units total, on a
0.75-acre urban infill lot (roughly 130ft x 250ft). Do not render multiple
buildings, multiple wings, a large courtyard, or a pool — there is not
enough room. Count visible unit entries/balconies before finishing: if it
reads as more than about 32 units or more than one building, it is wrong.
Most of the site is surface parking and required setbacks, not amenity
space. This must look buildable and plausible for city planning approval
on this specific lot size — not a resort or luxury complex."

## Camera rule
Maintain the exact camera position wherever possible within a sequence
(hero-existing -> build-finished). Only construction should evolve.

## Sequence (each row's Upload is the previous row's Output)

| # | File | Upload | What changes |
|---|------|--------|---------------|
| 01 | hero-existing.jpg | DONE (2026-08-11, native 1536x1024) | — |
| 02 | build-prep.jpg | DONE (2026-08-11, native 1536x1024) | — |
| 03 | build-foundation.jpg | DONE (2026-08-11, native 1536x1024, via ChatGPT browser automation) | — |
| 04 | build-framing.jpg | DONE (2026-08-11, native 1536x1024, via ChatGPT browser automation) | — |
| 05 | build-shell.jpg | DONE (2026-08-11, native 1536x1024, via ChatGPT browser automation) | — |
| 06 | build-finished.jpg | DONE (2026-08-11, native 1536x1024, via ChatGPT browser automation, master reference) | — |

## Gallery — every image starts from build-finished.jpg (the master reference), camera moves only

| File | Camera |
|------|--------|
| gallery-front.jpg | Street-level, golden hour, entrance monument "5302" |
| gallery-corner.jpg | Corner of Georgia Ave & 35th Ave, full massing, single building visible |
| gallery-courtyard.jpg | Entry walkway/landscaped strip, no pool, no large courtyard |
| gallery-pool.jpg | Repurposed: elevation/detail shot — stucco, tile roof, balconies close-up |
| gallery-lobby.jpg | Interior lobby/leasing office, arches, wood beams |
| gallery-parking.jpg | Surface parking lot, rear elevation, EV charging |
| gallery-aerial.jpg | Low-altitude drone, full 0.75-acre parcel, neighborhood preserved, confirms single-building scale |
| gallery-night.jpg | Same camera as gallery-front, night, warm glow |

## Final rule
Not concept art — an architect's investor-presentation render. Everything
must appear fully buildable, correctly scaled, and visually consistent
across every image.
