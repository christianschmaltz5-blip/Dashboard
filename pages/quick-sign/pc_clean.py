#!/usr/bin/env python3
"""Clean up the Property Condition Disclosure checkbox/comment formatting.
Runs the normal pixel detector, then:
  - makes every Yes/No/Do-Not-Know/N-A checkbox a uniform square,
  - snaps checkboxes to aligned columns (per page, from their own x-clusters),
  - removes doubled/overlapping checkboxes and comment boxes,
  - drops tall phantom boxes.
Layout-agnostic: works across the single- and multi-table pages.
"""
import fitz, cv2, numpy as np, json, os, sys
import render_detect as rd

WORKDIR = os.path.dirname(os.path.abspath(__file__))
CB = 11.0  # uniform checkbox side, pt


def clusters(vals, gap):
    if not vals: return []
    vals = sorted(vals); out = []; cur = [vals[0]]
    for v in vals[1:]:
        if v - cur[-1] <= gap: cur.append(v)
        else: out.append((sum(cur)/len(cur), len(cur))); cur = [v]
    out.append((sum(cur)/len(cur), len(cur)))
    return out


def area(f): return f["w"]*f["h"]


def overlap_frac(a, b):
    ax0, ay0, ax1, ay1 = a["x"], a["y"], a["x"]+a["w"], a["y"]+a["h"]
    bx0, by0, bx1, by1 = b["x"], b["y"], b["x"]+b["w"], b["y"]+b["h"]
    ix = max(0, min(ax1, bx1)-max(ax0, bx0)); iy = max(0, min(ay1, by1)-max(ay0, by0))
    inter = ix*iy
    return inter/min(area(a), area(b)) if min(area(a), area(b)) else 0


def clean_page(page):
    fields, W, H = rd.detect(page)
    others = [f for f in fields if f["type"] != "checkbox"]
    # checkboxes straight from the reliable pixel pass (detect() drops ones that
    # sit inside a larger box, which loses whole columns on dense pages)
    S = rd.S
    pix = page.get_pixmap(matrix=fitz.Matrix(S, S))
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_RGB2GRAY)
    ink = (gray < 140).astype(np.uint8)*255
    words = rd.words_px(page)
    checks = rd.checkbox_pixels(ink, words, pix.width, pix.height, W, H)

    # ---- checkboxes: uniform size + column snap + dedupe ----
    xs = [(f["x"]+f["w"]/2)*W for f in checks]
    cols = [c for c, n in clusters(xs, 9) if n >= 2]
    cw, ch = CB/W, CB/H
    out_checks = []
    for f in checks:
        cx = (f["x"]+f["w"]/2)*W; cy = (f["y"]+f["h"]/2)*H
        near = min(cols, key=lambda c: abs(c-cx)) if cols else cx
        if cols and abs(near-cx) <= 14:
            cx = near
        nf = {"type": "checkbox", "kind": "checkbox", "label": "",
              "x": round((cx-CB/2)/W, 5), "y": round((cy-CB/2)/H, 5), "w": round(cw, 5), "h": round(ch, 5)}
        if any(abs((g["x"]-nf["x"])) < 0.006 and abs(g["y"]-nf["y"]) < 0.006 for g in out_checks):
            continue
        out_checks.append(nf)

    # ---- comment / text boxes: drop tall phantoms, dedupe overlaps (keep larger) ----
    texts = [f for f in others if f["type"] in ("text",)]
    rest = [f for f in others if f["type"] not in ("text",)]
    # drop tall phantoms and stray fields in the leftmost row-number column
    texts = [f for f in texts if f["h"]*H <= 95 and (f["x"]+f["w"]/2)*W > 62]
    texts.sort(key=area, reverse=True)
    kept = []
    for f in texts:
        if any(overlap_frac(f, g) > 0.45 for g in kept):
            continue
        kept.append(f)

    return {"page": None, "w": W, "h": H, "fields": rest + kept + out_checks}


def process(path):
    doc = fitz.open(path); pages = []
    for p in range(doc.page_count):
        pg = clean_page(doc[p]); pg["page"] = p; pages.append(pg)
    doc.close(); return pages


def debug(path, man, out_png, page=0):
    doc = fitz.open(path); pgo = doc[page]
    pgo.get_pixmap(matrix=fitz.Matrix(2, 2)).save(out_png)
    from PIL import Image, ImageDraw
    im = Image.open(out_png).convert("RGB"); d = ImageDraw.Draw(im)
    W, H = man[page]["w"], man[page]["h"]
    for f in man[page]["fields"]:
        x0 = f["x"]*W*2; y0 = f["y"]*H*2; x1 = (f["x"]+f["w"])*W*2; y1 = (f["y"]+f["h"])*H*2
        c = (0, 160, 90) if f["type"] == "date" else (37, 99, 235)
        d.rectangle([x0, y0, x1, y1], outline=c, width=2)
    im.save(out_png); doc.close()


if __name__ == "__main__":
    name = "property-condition"
    path = os.path.join(WORKDIR, "forms", name+".pdf")
    man = process(path)
    print(f"{name}: {len(man)} pages, {sum(len(p['fields']) for p in man)} fields")
    from collections import Counter
    for p in man:
        print(f"  page {p['page']}: {dict(Counter(f['type'] for f in p['fields']))}")
    json.dump(man, open(os.path.join(WORKDIR, name+".fields.json"), "w"), indent=1)
    debug(path, man, os.path.join(WORKDIR, name+"_cdebug.png"), page=int(sys.argv[1]) if len(sys.argv) > 1 else 0)
