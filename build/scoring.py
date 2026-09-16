"""Apartment scoring -> green / orange / yellow tiers.

Weights follow the sales team's priorities (Sept 2026):
  condition (manual, 1-5) ×3    — most important
  bed quality                   — important: real beds > sofa beds
  balcony / dishwasher / TV     — nice to have (0.5 each)
  space per guest               — only matters when really tight
  rare extras (AC, washer...)   — minor
Tier thresholds are computed from the distribution so the fleet splits roughly in thirds.
"""
import re

SOFA = re.compile(r'sofa|pull-?out', re.I)
REAL_DOUBLE = re.compile(r'^(?!.*(sofa|bunk)).*double bed', re.I)


def bed_points(a):
    spec = a['bedSpec']
    has_double = any(REAL_DOUBLE.search(b) for b in spec)
    sofa_units = 0
    for b in spec:
        if SOFA.search(b):
            m = re.match(r'^(\d+)', b.strip())
            sofa_units += int(m.group(1)) if m else 1
    has_single = any(re.search(r'single bed', b, re.I) for b in spec)
    pts = 0
    why = []
    if has_double:
        pts += 2; why.append('מיטה זוגית אמיתית +2')
    elif has_single:
        pts += 1; why.append('מיטת יחיד אמיתית +1')
    else:
        why.append('רק ספות/קומתיים 0')
    if sofa_units >= 2:
        pts -= 1; why.append(f'{sofa_units} ספות נפתחות −1')
    return pts, why


def space_points(a):
    if not a['sizeM2'] or not a['maxGuests']:
        return 0, []
    r = a['sizeM2'] / a['maxGuests']
    if r < 4.3:
        return -1, [f'צפוף: {r:.1f} מ״ר לאדם −1']
    return 0, [f'{r:.1f} מ״ר לאדם 0']


def score(a, manual):
    m = manual.get(a['id'], {})
    cond = m.get('condition')
    parts = []
    total = 0.0

    if cond is not None:
        p = cond * 3
        total += p; parts.append(f'מצב הדירה {cond}/5 → +{p:g}')
    else:
        parts.append('מצב הדירה: לא דורג')

    p, why = bed_points(a); total += p; parts += why
    p, why = space_points(a); total += p; parts += why

    for key, label in (('HAS_BALCONY_TERRASSE', 'מרפסת'), ('HAS_DISHWASHER', 'מדיח'), ('HAS_TV', 'טלוויזיה')):
        if key in a['amenities']:
            total += 0.5; parts.append(f'{label} +0.5')
        else:
            parts.append(f'בלי {label} 0')

    rare = [k for k in ('HAS_AIR_CONDITIONING', 'HAS_WASHER', 'HAS_ELEVATOR', 'HAS_COFFEE_MAKER') if k in a['amenities']]
    if rare:
        total += 0.5; parts.append(f'בונוסים ({len(rare)}) +0.5')

    return round(total, 1), parts


def apply(apartments, manual):
    for a in apartments:
        a['score'], a['scoreParts'] = score(a, manual)
        m = manual.get(a['id'], {})
        a['condition'] = m.get('condition')
        a['conditionNote'] = m.get('conditionNote')
        a['price'] = m.get('price')
    scores = sorted(a['score'] for a in apartments)
    lo = scores[len(scores) // 3]
    hi = scores[(2 * len(scores)) // 3]
    for a in apartments:
        a['tier'] = 'green' if a['score'] >= hi else ('orange' if a['score'] >= lo else 'yellow')
    return lo, hi
