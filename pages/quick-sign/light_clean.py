#!/usr/bin/env python3
"""Apply the Property-Condition-style cleanup to any form's detected layout:
uniform checkbox squares, snap to strong columns, dedupe overlapping checkboxes
and comment/text boxes, drop tall phantoms. Post-processes an existing
<key>.fields.json in place (no re-detection)."""
import json, os, sys

CB = 11.0  # uniform checkbox side, pt


def clusters(vals, gap):
    if not vals: return []
    vals = sorted(vals); out = []; cur = [vals[0]]
    for v in vals[1:]:
        if v-cur[-1] <= gap: cur.append(v)
        else: out.append((sum(cur)/len(cur), len(cur))); cur = [v]
    out.append((sum(cur)/len(cur), len(cur)))
    return out


def area(f): return f["w"]*f["h"]


def ov(a, b):
    ix = max(0, min(a["x"]+a["w"], b["x"]+b["w"])-max(a["x"], b["x"]))
    iy = max(0, min(a["y"]+a["h"], b["y"]+b["h"])-max(a["y"], b["y"]))
    inter = ix*iy; m = min(area(a), area(b))
    return inter/m if m else 0


def clean_page(pg):
    W, H = pg["w"], pg["h"]
    fields = pg["fields"]
    checks = [f for f in fields if f["type"] == "checkbox"]
    texts = [f for f in fields if f["type"] == "text"]
    rest = [f for f in fields if f["type"] not in ("checkbox", "text")]

    # checkboxes: uniform size, snap to strong columns (>=4 members), dedupe
    xs = [(f["x"]+f["w"]/2)*W for f in checks]
    cols = [c for c, n in clusters(xs, 9) if n >= 4]
    out_checks = []
    for f in checks:
        cx = (f["x"]+f["w"]/2)*W; cy = (f["y"]+f["h"]/2)*H
        if cy < 0.13*H:
            continue  # skip logo/header false positives (letter counters, etc.)
        if cols:
            near = min(cols, key=lambda c: abs(c-cx))
            if abs(near-cx) <= 13:
                cx = near
        nf = {"type": "checkbox", "kind": "checkbox", "label": "",
              "x": round((cx-CB/2)/W, 5), "y": round((cy-CB/2)/H, 5),
              "w": round(CB/W, 5), "h": round(CB/H, 5)}
        if any(abs(nf["x"]-g["x"]) < 0.006 and abs(nf["y"]-g["y"]) < 0.006 for g in out_checks):
            continue
        out_checks.append(nf)

    # comment/text boxes: drop tall phantoms, dedupe overlaps (keep larger)
    texts = [f for f in texts if f["h"]*H <= 95]
    texts.sort(key=area, reverse=True)
    kept = []
    for f in texts:
        if any(ov(f, g) > 0.45 for g in kept):
            continue
        kept.append(f)

    pg["fields"] = rest + kept + out_checks
    return pg


if __name__ == "__main__":
    WORKDIR = os.path.dirname(os.path.abspath(__file__))
    for key in sys.argv[1:]:
        path = os.path.join(WORKDIR, key+".fields.json")
        man = json.load(open(path))
        before = sum(len(p["fields"]) for p in man)
        for pg in man:
            clean_page(pg)
        after = sum(len(p["fields"]) for p in man)
        json.dump(man, open(path, "w"), indent=1)
        from collections import Counter
        types = Counter(f["type"] for p in man for f in p["fields"])
        print(f"{key:20} {before}->{after} fields  {dict(types)}")
