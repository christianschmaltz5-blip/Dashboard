#!/usr/bin/env python3
"""Retag mis-typed text fields as signature/date/initial and add missing
signature-line fields, driven by the PDF's own text layer. Edits manifests.js
in place (re-serialized as `window.QS_DOCS = <json>;`)."""
import json, re, sys
import fitz

MANIFEST = 'manifests.js'
DOCS_DIR = 'docs'

# docs whose PDFs still have a usable text layer (the other 3 — counter-offer,
# addendum, bill-of-sale — are handled purely visually, see curate_visual.py)
TARGET_KEYS = [
    'lease-kta', 'lease-harbor-audubon', 'lease-harbor-bennington',
    'lease-harbor-bomber', 'lease-harbor-silverton', 'lease-freedom-estates',
    'lease-harbor-audubon-2025', 'lease-harbor-silverton-v1',
    'estimated-proceeds',
]

ROLE_WORDS = {'tenant', 'landlord', 'owner', 'resident', 'agent', 'seller',
              'buyer', 'tenant(s)', 'landlord/agent', "tenant's", 'grantor', 'grantee'}
NON_MATCH_HINTS = ('birth', 'garage', 'keys', 'received', 'address', 'number',
                    'license', 'phone', 'email', 'due', 'term', 'move-in',
                    'move in', 'occupan')
UNDERSCORE_RE = re.compile(r'^_{3,}$')


def classify(text):
    if not text:
        return None
    t = text.strip().strip(':').lower()
    if not t:
        return None
    if any(h in t for h in NON_MATCH_HINTS):
        return None
    if 'signature' in t or re.search(r'\bsign(ed)?\b', t):
        return 'signature'
    if t in ROLE_WORDS:
        return 'signature'
    if 'initial' in t:
        return 'initial'
    if re.search(r'\bdate[d]?\b', t):
        return 'date'
    return None


def group_lines(words):
    """group get_text('words') tuples by (block_no, line_no)."""
    lines = {}
    for w in words:
        key = (w[5], w[6])
        lines.setdefault(key, []).append(w)
    for key in lines:
        lines[key].sort(key=lambda w: w[0])
    return lines


def line_bbox(line_words):
    y0 = min(w[1] for w in line_words)
    y1 = max(w[3] for w in line_words)
    x0 = min(w[0] for w in line_words)
    x1 = max(w[2] for w in line_words)
    return x0, y0, x1, y1


def best_overlapping_line(lines, fx0, fx1, fy0, fy1):
    # Multiple blocks (e.g. side-by-side columns) can share the same y-band,
    # so a match must also sit near the field horizontally, not just overlap
    # in y — otherwise a 3-column signature row picks the wrong column.
    best_key, best_frac = None, 0.0
    for key, lw in lines.items():
        _, ly0, _, ly1 = line_bbox(lw)
        inter = max(0.0, min(fy1, ly1) - max(fy0, ly0))
        frac = inter / max(1e-6, (fy1 - fy0))
        if frac <= 0.25:
            continue
        if not any(fx0 - 30 <= (w[0] + w[2]) / 2 <= fx1 + 30 for w in lw):
            continue
        if frac > best_frac:
            best_frac, best_key = frac, key
    return best_key


def label_for_field(lines, fx0, fy0, fx1, fy1):
    """Return (before_text, after_text, below_text) around a field bbox."""
    key = best_overlapping_line(lines, fx0, fx1, fy0, fy1)
    before, after, below = '', '', ''
    if key is not None:
        lw = lines[key]
        before_words = [w[4] for w in lw if w[2] <= fx0 + 3 and not UNDERSCORE_RE.match(w[4])]
        after_words = [w[4] for w in lw if w[0] >= fx1 - 3 and not UNDERSCORE_RE.match(w[4])]
        before = before_words[-1] if before_words else ''
        after = ' '.join(after_words)
        blk, ln = key
        below_key = (blk, ln + 1)
        if below_key in lines:
            # restrict to words whose horizontal center falls within this
            # field's own column (padded a little) so a multi-column row of
            # labels (e.g. "Signature of Landlord | Signature of Tenant(s) |
            # Inspection Date") doesn't bleed into a neighboring field's label
            blw = [w for w in lines[below_key] if fx0 - 10 <= (w[0] + w[2]) / 2 <= fx1 + 10]
            below = ' '.join(w[4] for w in sorted(blw, key=lambda w: w[0]))
    return before, after, below


def classify_field(lines, fx0, fy0, fx1, fy1):
    before, after, below = label_for_field(lines, fx0, fy0, fx1, fy1)
    for cand in (before, after, below):
        t = classify(cand)
        if t:
            return t
    return None


def overlaps(fx0, fy0, fx1, fy1, wx0, wy0, wx1, wy1):
    ix = max(0.0, min(fx1, wx1) - max(fx0, wx0))
    iy = max(0.0, min(fy1, wy1) - max(fy0, wy0))
    inter = ix * iy
    warea = max(1e-6, (wx1 - wx0) * (wy1 - wy0))
    return inter / warea


def process_doc(d):
    key = d['key']
    path = f'{DOCS_DIR}/{key}.pdf'
    doc = fitz.open(path)
    before_counts, after_counts = {}, {}
    added, retagged = [], []

    for pg in d.get('layout', []):
        pno = pg['page']
        if pno >= len(doc):
            continue
        page = doc[pno]
        pgw, pgh = pg['w'], pg['h']
        words = page.get_text('words')
        lines = group_lines(words)
        fields = pg.get('fields', [])

        for f in fields:
            before_counts[f['type']] = before_counts.get(f['type'], 0) + 1

        # 1) retag existing text fields
        for f in fields:
            if f['type'] != 'text':
                continue
            fx0, fy0 = f['x'] * pgw, f['y'] * pgh
            fx1, fy1 = fx0 + f['w'] * pgw, fy0 + f['h'] * pgh
            newtype = classify_field(lines, fx0, fy0, fx1, fy1)
            if newtype:
                retagged.append((key, pno, f['x'], f['y'], f['type'], newtype))
                f['type'] = newtype

        # 2) find underscore blanks not covered by any field -> add new ones
        underscore_words = [w for w in words if UNDERSCORE_RE.match(w[4])]
        for w in underscore_words:
            wx0, wy0, wx1, wy1 = w[0], w[1], w[2], w[3]
            covered = False
            for f in fields:
                fx0, fy0 = f['x'] * pgw, f['y'] * pgh
                fx1, fy1 = fx0 + f['w'] * pgw, fy0 + f['h'] * pgh
                if overlaps(fx0, fy0, fx1, fy1, wx0, wy0, wx1, wy1) > 0.3:
                    covered = True
                    break
            if covered:
                continue
            newtype = classify_field(lines, wx0, wy0, wx1, wy1)
            if not newtype:
                continue
            # size the new box to the blank line, with a touch of vertical pad
            h_pts = max(wy1 - wy0 + 4, pgh * 0.022)
            h_pts = min(h_pts, pgh * 0.03)
            y0_pts = wy0 - 2
            nf = {
                'type': newtype, 'kind': newtype, 'label': '',
                'x': round(wx0 / pgw, 5), 'y': round(y0_pts / pgh, 5),
                'w': round((wx1 - wx0) / pgw, 5), 'h': round(h_pts / pgh, 5),
            }
            fields.append(nf)
            added.append((key, pno, newtype, nf['x'], nf['y']))

        for f in fields:
            after_counts[f['type']] = after_counts.get(f['type'], 0) + 1

    d['fieldCount'] = sum(after_counts.values())
    return before_counts, after_counts, added, retagged


def main():
    txt = open(MANIFEST, encoding='utf-8').read()
    m = re.search(r'window\.QS_DOCS\s*=\s*(\[.*\]);?\s*$', txt, re.S)
    data = json.loads(m.group(1))

    report = []
    for d in data:
        if d['key'] not in TARGET_KEYS:
            continue
        before, after, added, retagged = process_doc(d)
        report.append((d['key'], before, after, added, retagged))

    out = 'window.QS_DOCS = ' + json.dumps(data, separators=(',', ':')) + ';'
    with open(MANIFEST, 'w', encoding='utf-8') as fh:
        fh.write(out)

    for key, before, after, added, retagged in report:
        print(f'=== {key} ===')
        print('  before:', before)
        print('  after: ', after)
        for r in retagged:
            print('  retag:', r)
        for a in added:
            print('  add:  ', a)

    if len(sys.argv) > 1 and sys.argv[1] == '--report-json':
        json.dump(report, open('/tmp/curate_report.json', 'w'))


if __name__ == '__main__':
    main()
