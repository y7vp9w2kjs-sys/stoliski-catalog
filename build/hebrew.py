"""Rule-based Hebrew rendering of the (very uniform) Hostfully listing text.

Anything that doesn't match a known pattern is left in English and reported,
so new phrasing in Hostfully shows up in the build log instead of silently
appearing untranslated.
"""
import re

UNKNOWN = set()

BED_TYPES = [  # (regex on the lower-cased type, singular, plural)
    (r'(bunk double|couple bunk|double bunk) beds?', 'מיטת קומתיים זוגית', 'מיטות קומתיים זוגיות'),
    (r'(double sofa|sofa double) beds?', 'ספה נפתחת זוגית', 'ספות נפתחות זוגיות'),
    (r'sofa beds?', 'ספה נפתחת', 'ספות נפתחות'),
    (r'bunk beds?', 'מיטת קומתיים', 'מיטות קומתיים'),
    (r'double beds?', 'מיטה זוגית', 'מיטות זוגיות'),
    (r'single beds?', 'מיטת יחיד', 'מיטות יחיד'),
    (r'pull-?out beds? \(under the sofa\)', 'מיטה נשלפת (מתחת לספה)', 'מיטות נשלפות (מתחת לספה)'),
    (r'pull-?out beds? \(under the bunk-?bed\)', 'מיטה נשלפת (מתחת למיטת הקומתיים)', 'מיטות נשלפות (מתחת למיטת הקומתיים)'),
]


def bed_line(line):
    s = line.strip()
    m = re.match(r'^(\d+)?\s*(.+?)\s*(?:\(\s*(?:for\s*)?(\d+)\s*\))?$', s)
    if not m:
        UNKNOWN.add(('bed', s)); return s
    count = int(m.group(1) or 1)
    kind = m.group(2).strip().lower()
    cap = m.group(3)
    for rx, sing, plur in BED_TYPES:
        if re.fullmatch(rx, kind):
            name = sing if count == 1 else f'{count} {plur}'
            if cap:
                name += f' (ל-{cap})'
            return name
    UNKNOWN.add(('bed', s)); return s


def perfect_for(s):
    s = (s or '').strip()
    if not s:
        return ''
    m = re.match(r'^Family \((\d+)-(\d+) kids\) or (\d+)-(\d+) friends$', s, re.I)
    if m:
        a, b, c, d = m.groups()
        return f'משפחה ({a}–{b} ילדים) או {c}–{d} חברים'
    m = re.match(r'^Couple or (\d+)-(\d+) friends$', s, re.I)
    if m:
        return f'זוג או {m.group(1)}–{m.group(2)} חברים'
    m = re.match(r'^Couple or (\d+) friends$', s, re.I)
    if m:
        return f'זוג או {m.group(1)} חברים'
    UNKNOWN.add(('perfectFor', s)); return s


FEATURES = {
    'direct ski-in/ski-out access': 'גישה ישירה למסלולים (Ski-in / Ski-out)',
    'fully equipped kitchen': 'מטבח מאובזר במלואו',
    'heating and hot water': 'חימום ומים חמים',
    'ski rental store nearby': 'חנות השכרת ציוד סקי בקרבת מקום',
    'balcony with mountain views': 'מרפסת עם נוף להרים',
    'tv included': 'טלוויזיה',
    'comfortable double bed': 'מיטה זוגית נוחה',
    'coffee machine': 'מכונת קפה',
}


def feature(s):
    k = s.strip().rstrip('.').lower()
    if k in FEATURES:
        return FEATURES[k]
    m = re.match(r'^(\d+) comfortable beds?$', k)
    if m:
        return f'{m.group(1)} מיטות נוחות'
    UNKNOWN.add(('feature', s)); return s


def extra(s):
    k = s.strip().strip('"').rstrip('.').lower()
    if k.startswith('linen and towels available for'):
        m = re.search(r'€\s*(\d+)', s)
        return f'מצעים ומגבות: {m.group(1) if m else "?"}€ לאורח (אופציונלי)'
    if k == 'huge apartment!':
        return 'דירה ענקית!'
    if k.startswith('ski-in/ski-out,'):
        return None  # duplicated headline, drop
    UNKNOWN.add(('extra', s)); return s


def headline(s):
    s = (s or '').strip()
    if not s:
        return ''
    m = re.match(r'^Ski-in/Ski-out, (\d+)\s*-Bed Apartment in Val Thorens(?: \(up to (\d+) people\))?\.?$', s, re.I)
    if m:
        n, up = m.groups()
        out = f'דירת {n} מיטות בואל טורנס עם גישה ישירה למסלולים (Ski-in / Ski-out)'
        if up:
            out += f', עד {up} אנשים'
        return out
    UNKNOWN.add(('headline', s)); return s


CHECKIN = {
    'Key box': 'תיבת מפתחות (קוד)',
    'Reception / doorman': 'קבלה / שוער',
    'Other (keys inside)': 'הדירה פתוחה, המפתחות בפנים',
}


def apply(a):
    """Add *He fields to a normalized apartment record (in place)."""
    a['headlineHe'] = headline(a['headline'])
    a['perfectForHe'] = perfect_for(a['perfectFor'])
    a['bedSpecHe'] = [bed_line(b) for b in a['bedSpec']]
    a['featuresHe'] = [feature(f) for f in a['features']]
    a['extrasHe'] = [x for x in (extra(e) for e in a['extras']) if x]
    a['checkInMethodHe'] = CHECKIN.get(a['checkInMethod'] or '', a['checkInMethod'])
    parts = [a['headlineHe']]
    if a['perfectForHe']:
        parts.append('מתאים ל: ' + a['perfectForHe'])
    if a['featuresHe']:
        parts.append('\n'.join('• ' + f for f in a['featuresHe']))
    if a['extrasHe']:
        parts.append('\n'.join(a['extrasHe']))
    if a['bedSpecHe']:
        parts.append('סידור מיטות:\n' + '\n'.join('• ' + b for b in a['bedSpecHe']))
    a['descriptionHe'] = '\n\n'.join(p for p in parts if p)
    return a


# ---------------------------------------------------------------------------
# Tignes listings are written as prose instead of the Val Thorens bullet format,
# so they need their own parser. Same rule-based approach: anything unmatched is
# reported rather than silently left in English.

WORDNUM = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6}

PROSE_BEDS = [
    (r'fold-?down single beds?', 'מיטת יחיד מתקפלת', 'מיטות יחיד מתקפלות'),
    (r'bunk beds?', 'מיטת קומתיים', 'מיטות קומתיים'),
    (r'sofa beds?', 'ספה נפתחת', 'ספות נפתחות'),
    (r'double beds?', 'מיטה זוגית', 'מיטות זוגיות'),
    (r'single beds?', 'מיטת יחיד', 'מיטות יחיד'),
]

PROSE_FEATURES = [
    (r'\bbalcony\b', 'מרפסת'),
    (r'mountain views?', 'נוף להרים'),
    (r'\bkitchenette\b', 'מטבחון מאובזר'),
    (r'washing machine', 'מכונת כביסה בדירה'),
    (r'\bTV\b', 'טלוויזיה'),
    (r'dining (?:table|space)', 'פינת אוכל'),
    (r'bathtub with shower', 'אמבטיה עם מקלחת'),
    (r'bathroom has a shower', 'מקלחת'),
    (r'coffee maker', 'מכונת קפה'),
    (r'\bmicrowave\b', 'מיקרוגל'),
    (r'refrigerator', 'מקרר'),
    (r'\bkettle\b', 'קומקום'),
    (r'\bhob\b', 'כיריים'),
]


def _prose_bed(phrase):
    phrase = phrase.strip().lower()
    # "one double bed for two guests" -> "one double bed"
    phrase = re.sub(r'\s+for\s+[\w-]+\s+guests?$', '', phrase).strip()
    m = re.match(r'^(\w+)\s+(.*)$', phrase)
    count, kind = 1, phrase
    if m and m.group(1) in WORDNUM:
        count, kind = WORDNUM[m.group(1)], m.group(2)
    elif m and m.group(1).isdigit():
        count, kind = int(m.group(1)), m.group(2)
    kind = kind.strip()
    for rx, sing, plur in PROSE_BEDS:
        if re.fullmatch(rx, kind):
            return sing if count == 1 else f'{count} {plur}'
    UNKNOWN.add(('prose-bed', phrase))
    return phrase


def parse_prose(text, max_guests, resort):
    """Pull bed layout + features out of a prose listing description."""
    out = {'headline': '', 'perfectFor': '', 'bedSpec': [], 'features': [], 'extras': []}
    if not text:
        return out
    flat = ' '.join(text.split())

    m = re.search(r'Sleeping arrangement:\s*([^.;]+(?:;[^.]*)?)\.', flat, re.I)
    if m:
        seg = re.split(r';', m.group(1))[0]
        for part in re.split(r',| and ', seg):
            part = part.strip()
            if part and not re.match(r'^maximum', part, re.I):
                out['bedSpec'].append(_prose_bed(part))

    for rx, label in PROSE_FEATURES:
        if re.search(rx, flat, re.I) and label not in out['features']:
            out['features'].append(label)

    n = max_guests or 0
    out['headline'] = f'סטודיו עם מרפסת ב{"טין" if resort == "Tignes" else "ואל טורנס"}' + (f', עד {n} אנשים' if n else '')
    if n >= 4:
        out['perfectFor'] = f'משפחה או עד {n} חברים'
    elif n == 2:
        out['perfectFor'] = 'זוג'
    return out


def apply_prose(a, raw_summary):
    """Use for records whose summary is prose (no bullet list)."""
    pr = parse_prose(raw_summary, a.get('maxGuests'), a.get('resort'))
    a['headlineHe'] = pr['headline']
    a['perfectForHe'] = pr['perfectFor']
    a['bedSpecHe'] = pr['bedSpec']
    a['featuresHe'] = pr['features']
    a['extrasHe'] = []
    a['checkInMethodHe'] = CHECKIN.get(a.get('checkInMethod') or '', a.get('checkInMethod'))
    parts = [a['headlineHe']]
    if a['perfectForHe']:
        parts.append('מתאים ל: ' + a['perfectForHe'])
    if a['featuresHe']:
        parts.append('\n'.join('• ' + f for f in a['featuresHe']))
    if a['bedSpecHe']:
        parts.append('סידור מיטות:\n' + '\n'.join('• ' + b for b in a['bedSpecHe']))
    a['descriptionHe'] = '\n\n'.join(p for p in parts if p)
    return a
