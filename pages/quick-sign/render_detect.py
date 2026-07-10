#!/usr/bin/env python3
"""Pixel-based blank detector: find every VISIBLE horizontal line and box border
on each page and emit a blue field fitted to it. Works regardless of how the blank
is encoded (underscore text, vector stroke, or font underline).

Boxes  -> field fills the box interior.
Lines  -> field sits on the line, spanning its full width.
Filters: phantom boxes that sit on top of body text, header/footer rules,
and box top/bottom borders (so a box isn't also detected as two lines).
"""
import fitz, cv2, numpy as np, json, sys, os
from collections import namedtuple

WORKDIR = os.path.dirname(os.path.abspath(__file__))
FORMS = os.path.join(WORKDIR, "forms")
S = 2  # raster scale: 1pt -> 2px

DATEWORDS = ("date",)
SIGWORDS = ("signature", "sign", "buyer", "seller", "purchaser", "agent", "broker", "witness", "by:", "x")


def words_px(page):
    out = []
    for w in page.get_text("words"):
        out.append((w[0]*S, w[1]*S, w[2]*S, w[3]*S, w[4]))
    return out


def label_for(words, x0, y0, x1, y1):
    """Nearest label left (same row) or below."""
    yc = (y0+y1)/2
    left, below = [], []
    for wx0, wy0, wx1, wy1, txt in words:
        if not txt.strip():
            continue
        wyc = (wy0+wy1)/2
        if abs(wyc-yc) < 14 and wx1 <= x0+8 and (x0-wx1) < 340:
            left.append((wx1, txt))
        if 0 <= (wy0-y1) < 26 and wx0 < x1 and wx1 > x0-8:
            below.append((wx0, txt))
    left.sort(); below.sort()
    lt = " ".join(t for _, t in left[-6:]).strip()
    bt = " ".join(t for _, t in below[:4]).strip()
    return lt, bt


def classify(w, h, lt, bt):
    blob = (lt+" "+bt).lower()
    padded = " "+blob+" "
    if "signature" in blob or " sign " in padded:      # signature wins over a nearby "Date"
        return "signature"
    if any(k in blob for k in DATEWORDS):
        return "date"
    if "initial" in blob:
        return "initial"
    if any((" "+k+" ") in padded for k in SIGWORDS):
        return "signature"
    if h > 34 and w < 130:
        return "initial"
    return "text"


def checkbox_pixels(ink, words, PW, PH, W, H):
    """Detect small hollow squares (checkboxes) from pixels."""
    out = []
    cnts, _ = cv2.findContours(ink, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    seen = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if not (10 <= w <= 30 and 10 <= h <= 30 and abs(w-h) <= 8):
            continue
        area = cv2.contourArea(c)
        if area < 0.35*w*h:            # must roughly fill its bbox (a frame does)
            continue
        interior = ink[y+3:y+h-3, x+3:x+w-3]
        if interior.size and interior.mean() > 60:   # not hollow -> a glyph, skip
            continue
        cx, cy = x+w/2, y+h/2
        if any(abs(cx-sx) < w and abs(cy-sy) < h for sx, sy in seen):
            continue
        # skip if a text word sits exactly on it (letters)
        if any(wx0-2 <= cx <= wx1+2 and wy0-2 <= cy <= wy1+2 and (wx1-wx0) > 6
               for wx0, wy0, wx1, wy1, t in words if t.strip()):
            continue
        seen.append((cx, cy))
        out.append(mk("checkbox", "checkbox", x, y, w, h, W, H, PW, PH, ""))
    return out


def checkbox_fields(page, PW, PH, W, H):
    """Vector pass for small square checkboxes (the pixel pass skips them)."""
    out = []
    for dr in page.get_drawings():
        for it in dr["items"]:
            if it[0] == "re":
                r = it[1]; rw, rh = r.x1-r.x0, r.y1-r.y0
                if 5 <= rw <= 17 and 5 <= rh <= 17 and abs(rw-rh) < 6:
                    out.append(mk("checkbox", "checkbox", r.x0*S, r.y0*S, rw*S, rh*S, W, H, PW, PH, ""))
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                fn = s.get("font", "").lower()
                if any(ch in s["text"] for ch in "❏❍☐❑□■") or ("dingbat" in fn and s["text"].strip() in ("q", "o", "m")):
                    bx = s["bbox"]
                    out.append(mk("checkbox", "checkbox", bx[0]*S, bx[1]*S, (bx[2]-bx[0])*S, (bx[3]-bx[1])*S, W, H, PW, PH, ""))
    return out


def text_words_inside(words, x0, y0, x1, y1, pad=6):
    n = 0
    for wx0, wy0, wx1, wy1, txt in words:
        if not txt.strip():
            continue
        cx, cy = (wx0+wx1)/2, (wy0+wy1)/2
        if x0+pad < cx < x1-pad and y0+pad < cy < y1-pad:
            n += 1
    return n


def text_above_frac(words, x0, x1, y):
    """Fraction of the line's width that has text sitting just above it."""
    line_w = x1-x0
    if line_w <= 0:
        return 1.0
    cover = np.zeros(int(line_w)+1, dtype=bool)
    for wx0, wy0, wx1, wy1, txt in words:
        if not txt.strip():
            continue
        if -2 <= (y - wy1) < 16:          # word baseline sits just above the line
            a = int(max(0, wx0-x0)); b = int(min(line_w, wx1-x0))
            if b > a:
                cover[a:b] = True
    return cover.mean()


def detect(page):
    W, H = page.rect.width, page.rect.height
    pix = page.get_pixmap(matrix=fitz.Matrix(S, S))
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_RGB2GRAY) if pix.n >= 3 else img[:, :, 0]
    ink = (gray < 140).astype(np.uint8) * 255
    PW, PH = pix.width, pix.height
    words = words_px(page)

    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (38, 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 26))
    Hmask = cv2.morphologyEx(ink, cv2.MORPH_OPEN, hk)
    Vmask = cv2.morphologyEx(ink, cv2.MORPH_OPEN, vk)

    # ---- boxes: rectangles formed by H+V strokes ----
    boxmask = cv2.dilate(cv2.bitwise_or(Hmask, Vmask), np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(boxmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if w < 34 or h < 22:
            continue
        if w > 0.94*PW and h > 0.9*PH:
            continue                                   # page frame
        # require it to actually be a frame (H top&bottom + V sides), not a text blob
        sub_h = Hmask[y:y+h, x:x+w].mean()
        sub_v = Vmask[y:y+h, x:x+w].mean()
        if sub_h < 3 or sub_v < 3:
            continue
        if text_words_inside(words, x, y, x+w, y+h) > 3:  # phantom box over paragraph
            continue
        boxes.append((x, y, w, h))

    # ---- horizontal lines (underline blanks) ----
    hc, _ = cv2.findContours(Hmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    lines = []
    for c in hc:
        x, y, w, h = cv2.boundingRect(c)
        if w < 34 or h > 6:
            continue
        if w > 0.9*PW and (y < 90 or y > PH-70):
            continue                                   # header/footer rule
        on_box = any(abs(y-(by)) < 6 or abs(y-(by+bh)) < 6
                     for bx, by, bw, bh in boxes
                     if bx-6 <= x and x+w <= bx+bw+6)
        if on_box:
            continue
        if text_above_frac(words, x, x+w, y) > 0.55:   # underline of a heading, not a blank
            continue
        lines.append((x, y, w))

    # ---- build fields (normalize to fractions, origin top-left) ----
    fields = []
    for x, y, w, h in boxes:
        fx, fy, fw, fh = x+2, y+2, w-4, h-4
        lt, bt = label_for(words, fx, fy, fx+fw, fy+fh)
        fields.append(mk("box", classify(fw/S, fh/S, lt, bt), fx, fy, fw, fh, W, H, PW, PH, lt or bt))
    for x, y, w in lines:
        fh = 15*S
        fy = y - fh + 2
        lt, bt = label_for(words, x, fy, x+w, y)
        fields.append(mk("line", classify(w/S, 15, lt, bt), x, fy, w, fh, W, H, PW, PH, lt or bt))
    cb = checkbox_fields(page, PW, PH, W, H)
    if not cb and len(words) > 10:   # pixel checkboxes only when a real text layer exists
        cb = checkbox_pixels(ink, words, PW, PH, W, H)
    fields += cb

    # dedupe overlaps
    fields.sort(key=lambda f: (f["y"], f["x"]))
    out = []
    for f in fields:
        if any(_overlap(f, g) > 0.6 for g in out):
            continue
        out.append(f)
    return out, W, H


def _overlap(a, b):
    ax0, ay0, ax1, ay1 = a["x"], a["y"], a["x"]+a["w"], a["y"]+a["h"]
    bx0, by0, bx1, by1 = b["x"], b["y"], b["x"]+b["w"], b["y"]+b["h"]
    ix = max(0, min(ax1, bx1)-max(ax0, bx0)); iy = max(0, min(ay1, by1)-max(ay0, by0))
    inter = ix*iy; ar = a["w"]*a["h"]
    return inter/ar if ar else 0


def mk(kind, ftype, xpx, ypx, wpx, hpx, W, H, PW, PH, label):
    return {"type": ftype, "kind": kind, "label": label[:36],
            "x": round(xpx/PW, 5), "y": round(ypx/PH, 5),
            "w": round(wpx/PW, 5), "h": round(hpx/PH, 5)}


def process(path):
    doc = fitz.open(path)
    pages = []
    for p in range(doc.page_count):
        fs, W, H = detect(doc[p])
        pages.append({"page": p, "w": W, "h": H, "fields": fs})
    doc.close()
    return pages


def debug(path, man, out_png, page=0):
    doc = fitz.open(path); pg = doc[page]
    pix = pg.get_pixmap(matrix=fitz.Matrix(2, 2)); pix.save(out_png)
    from PIL import Image, ImageDraw
    im = Image.open(out_png).convert("RGB"); d = ImageDraw.Draw(im)
    W, H = man[page]["w"], man[page]["h"]
    col = {"date": (0, 160, 90), "signature": (37, 99, 235), "initial": (200, 120, 0), "text": (37, 99, 235)}
    for f in man[page]["fields"]:
        x0 = f["x"]*W*2; y0 = f["y"]*H*2; x1 = (f["x"]+f["w"])*W*2; y1 = (f["y"]+f["h"])*H*2
        c = col.get(f["type"], (37, 99, 235))
        d.rectangle([x0, y0, x1, y1], outline=c, width=2)
    im.save(out_png); doc.close()


if __name__ == "__main__":
    name = sys.argv[1]
    path = os.path.join(FORMS, name+".pdf")
    man = process(path)
    print(f"{name}: {len(man)} pages, {sum(len(p['fields']) for p in man)} fields")
    for p in man:
        from collections import Counter
        print(f"  page {p['page']}: {dict(Counter(f['type'] for f in p['fields']))}")
    json.dump(man, open(os.path.join(WORKDIR, name+".fields.json"), "w"), indent=1)
    debug(path, man, os.path.join(WORKDIR, name+"_rdebug.png"), page=0)
