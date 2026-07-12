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

    # ---- comment boxes: one clean box per checkbox row, filling the comments cell ----
    hlines, comR = grid_info(ink, pix.width, pix.height, W, H)
    rest = [f for f in others if f["type"] != "text"]
    texts = [f for f in others if f["type"] == "text"]

    comment_boxes = []
    table_top = table_bot = None
    if out_checks and comR:
        # group checkboxes into rows by y-center
        rowc = clusters(sorted((c["y"]+c["h"]/2)*H for c in out_checks), 8)
        rowys = [c for c, n in rowc if n >= 2]
        if rowys:
            table_top, table_bot = min(rowys)-14, max(rowys)+14
            left_col = min((c["x"]+c["w"]/2)*W for c in out_checks)
            for ry in rowys:
                row_cx = [(c["x"]+c["w"]/2)*W for c in out_checks if abs((c["y"]+c["h"]/2)*H-ry) < 8]
                comL = max(row_cx)+15
                if comR-comL < 40:
                    continue
                ta = max([h for h in hlines if h < ry-2], default=ry-11)
                tb = min([h for h in hlines if h > ry+2], default=ry+11)
                ta = max(ta, ry-34); tb = min(tb, ry+34)   # guard against bridging gaps
                comment_boxes.append({"type": "text", "kind": "box", "label": "",
                                      "x": round((comL+2)/W, 5), "y": round((ta+1.5)/H, 5),
                                      "w": round((comR-comL-4)/W, 5), "h": round((tb-ta-3)/H, 5)})

    # keep text fields that are NOT in the table's checkbox/comments band
    kept = []
    for f in texts:
        cx = (f["x"]+f["w"]/2)*W; cy = (f["y"]+f["h"]/2)*H
        if f["h"]*H > 95 or cx < 62:
            continue
        if table_top is not None and table_top <= cy <= table_bot and cx > left_col-40:
            continue  # replaced by clean comment boxes
        kept.append(f)
    kept.sort(key=area, reverse=True)
    dedup = []
    for f in kept:
        if any(overlap_frac(f, g) > 0.45 for g in dedup):
            continue
        dedup.append(f)

    return {"page": None, "w": W, "h": H, "fields": rest + dedup + comment_boxes + out_checks}


def grid_info(ink, PW, PH, W, H):
    S = rd.S
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (150, 1))
    Hh = cv2.morphologyEx(ink, cv2.MORPH_OPEN, hk)
    hy = np.where(Hh.sum(axis=1) > 150*255)[0]
    hlines = [c/S for c, n in clusters(list(hy), 6)] if len(hy) else []
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 110))
    V = cv2.morphologyEx(ink, cv2.MORPH_OPEN, vk)
    vx = np.where(V.sum(axis=0) > 55*255)[0]
    vlines = [c/S for c, n in clusters(list(vx), 8)] if len(vx) else []
    comR = max(vlines) if vlines else W-14
    return hlines, comR


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
