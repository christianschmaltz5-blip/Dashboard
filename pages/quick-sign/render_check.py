#!/usr/bin/env python3
"""Rasterize each page of each doc with the manifest boxes overlaid,
color-coded by field type, for visual QA. Renders to the scratchpad dir."""
import re, json, sys, os
import fitz

MANIFEST = 'manifests.js'
DOCS_DIR = 'docs'
OUT_DIR = '/private/tmp/claude-501/-Users-christianschmaltz/55e8d284-18b8-4024-ba48-28f60e3ea0ab/scratchpad/qa-curate'
DPI = 130

COLORS = {
    'text': (0.2, 0.4, 0.9),
    'signature': (0.55, 0.2, 0.75),
    'date': (0.1, 0.65, 0.3),
    'initial': (0.9, 0.55, 0.05),
    'checkbox': (0.5, 0.5, 0.5),
}


def main():
    keys = sys.argv[1:] if len(sys.argv) > 1 else None
    txt = open(MANIFEST, encoding='utf-8').read()
    m = re.search(r'window\.QS_DOCS\s*=\s*(\[.*\]);?\s*$', txt, re.S)
    data = json.loads(m.group(1))
    os.makedirs(OUT_DIR, exist_ok=True)

    for d in data:
        if keys and d['key'] not in keys:
            continue
        path = f"{DOCS_DIR}/{d['key']}.pdf"
        doc = fitz.open(path)
        for pg in d.get('layout', []):
            pno = pg['page']
            if pno >= len(doc):
                continue
            page = doc[pno]
            zoom = DPI / 72.0
            out_path = f"{OUT_DIR}/{d['key']}-p{pno}.png"
            _render_with_boxes(page, pg, zoom, out_path)
        print('rendered', d['key'], '->', len([p for p in d['layout']]), 'pages')


def _render_with_boxes(page, pg, zoom, out_path):
    pw, ph = pg['w'], pg['h']
    # draw into a one-page clone of the source PDF so the boxes are baked
    # into real page content, then rasterize that.
    tmp = fitz.open()
    tmp.insert_pdf(page.parent, from_page=page.number, to_page=page.number)
    tpage = tmp[0]
    shape = tpage.new_shape()
    for f in pg.get('fields', []):
        x0, y0 = f['x'] * pw, f['y'] * ph
        x1, y1 = x0 + f['w'] * pw, y0 + f['h'] * ph
        color = COLORS.get(f['type'], (1, 0, 0))
        rect = fitz.Rect(x0, y0, x1, y1)
        shape.draw_rect(rect)
        shape.finish(color=color, width=1.4, fill=None)
    shape.commit()
    outpix = tpage.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    outpix.save(out_path)
    tmp.close()


if __name__ == '__main__':
    main()
