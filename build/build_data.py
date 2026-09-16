"""Normalize the raw Hostfully export into data/apartments.json and download photos.

Usage:
    python3 build/build_data.py path/to/raw_all32.json [--skip-images]

The raw file is the array produced by fetching, per property:
  /api/v3.2/properties/{uid}, /api/internal/property-descriptions,
  /api/v3.2/photos, /api/v3.2/amenities
Sensitive fields (key-box codes, wifi) are stripped and never written to disk.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hebrew  # noqa: E402
import scoring  # noqa: E402
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'data')
IMG_DIR = os.path.join(ROOT, 'images')

AMENITY_LABELS = {
    'HAS_SKI_IN_SKI_OUT': 'Ski-in / Ski-out',
    'HAS_BALCONY_TERRASSE': 'Balcony / terrace',
    'HAS_MOUNTAIN_VIEW': 'Mountain view',
    'HAS_MOUNTAIN': 'Mountain location',
    'HAS_KITCHEN': 'Kitchen',
    'HAS_KITCHENETTE': 'Kitchenette',
    'HAS_FRIDGE': 'Fridge',
    'HAS_MICROWAVE_OVEN': 'Microwave',
    'HAS_OVEN': 'Oven',
    'HAS_DISHWASHER': 'Dishwasher',
    'HAS_DINING_TABLE': 'Dining table',
    'HAS_COFFEE_MAKER': 'Coffee maker',
    'HAS_WATER_KETTLE': 'Kettle',
    'HAS_COOKING_BASICS': 'Cooking basics',
    'HAS_TV': 'TV',
    'HAS_HEATING': 'Heating',
    'HAS_HOT_WATER': 'Hot water',
    'HAS_AIR_CONDITIONING': 'Air conditioning',
    'HAS_WASHER': 'Washing machine',
    'HAS_ELEVATOR': 'Elevator',
}
CHECKIN_LABELS = {
    'lockbox': 'Key box',
    'doorman_entry': 'Reception / doorman',
    'other_checkin': 'Other (keys inside)',
}
# Amenities worth surfacing as filters / highlights (the rest are near-universal)
HIGHLIGHT_AMENITIES = [
    'HAS_SKI_IN_SKI_OUT', 'HAS_BALCONY_TERRASSE', 'HAS_DISHWASHER', 'HAS_TV',
    'HAS_AIR_CONDITIONING', 'HAS_WASHER', 'HAS_ELEVATOR', 'HAS_COFFEE_MAKER',
]

RESIDENCE_MAP = [
    ('Cime', 'Cimes de Caron'),
    ('Altineige', "Odalys L'Altineige"),
    ('Arcelle', "L'Arcelle"),
    ('Cusco', 'Machu Pichu (Cusco)'),
    ('Machu', 'Machu Pichu'),
    ('Pichu', 'Machu Pichu'),
    ('Dome', 'Le Dôme du Polset'),
    ('Joker', 'Le Joker'),
    ('La Vanoise', 'La Vanoise'),
    ('Lauzières', 'Les Lauzières'),
    ('Neves', 'Les Neves'),
    ('Olympiades', 'Olympiades'),
    ('Sérac', 'Le Sérac'),
]


def residence_for(list_name, address2):
    for prefix, label in RESIDENCE_MAP:
        if list_name.startswith(prefix):
            return label
    return (address2 or '').replace('Résidence', '').strip() or 'Unknown'


def code_from(public_name, list_name):
    unit = list_name.split()[-1].upper()  # "Lauzières 003" -> "003", "Joker C3" -> "C3"
    m = re.search(r'\(([A-Z]+)-([A-Z0-9]+)\)', public_name or '')
    if m:
        prefix, pub_unit = m.groups()
        # Some listings were cloned in Hostfully and still carry the source
        # unit's code (e.g. Lauzières 003 tagged LEZ-521); trust the list name.
        return f'{prefix}-{unit if pub_unit != unit else pub_unit}'
    return f'{list_name[0].upper()}-{unit}'


def parse_summary(summary):
    """Pull structured bits out of the free-text listing summary."""
    text = (summary or '').replace('\r', '')
    out = {'headline': '', 'perfectFor': '', 'features': [], 'bedSpec': [], 'extras': []}
    lines = [l.strip() for l in text.split('\n')]
    section = 'body'
    for l in lines:
        if not l:
            continue
        low = l.lower()
        if low.startswith('perfect for'):
            out['perfectFor'] = l.split(':', 1)[1].strip() if ':' in l else l
            continue
        if low.startswith('bed specification'):
            section = 'beds'
            continue
        if section == 'beds':
            out['bedSpec'].append(l)
            continue
        if l.startswith('*'):
            out['features'].append(l.lstrip('* ').strip())
            continue
        if not out['headline'] and low.startswith('ski-in'):
            out['headline'] = l
            continue
        if low.startswith('book your stay'):
            continue
        out['extras'].append(l)
    return out


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def normalize(raw):
    apartments = []
    for o in raw:
        p = o['property']
        d = (o['descriptions'] or [{}])[0]
        addr = p.get('address') or {}
        avail = p.get('availability') or {}
        list_name = o['listName'].strip()
        public_name = (d.get('name') or '').strip()
        code = code_from(public_name, list_name)
        parsed = parse_summary(d.get('summary'))

        amen_codes = []
        checkin = None
        for a in o['amenities']:
            key = a['amenity']
            if key == 'CHECK_IN_OPTION':
                checkin = CHECKIN_LABELS.get(a.get('description'), a.get('description'))
            elif key == 'CHECK_IN_OPTION_INSTRUCTION':
                continue  # key-box codes: never exported
            elif key in AMENITY_LABELS:
                amen_codes.append(key)

        photos = sorted(o['photos'], key=lambda x: x.get('displayOrder', 0))
        photo_entries = []
        for i, ph in enumerate(photos):
            photo_entries.append({
                'file': f'images/{slug(list_name)}/{i:02d}.jpg',
                'url': ph.get('mediumScaleImageUrl') or ph.get('largeScaleImageUrl') or ph.get('originalImageUrl'),
                'large': ph.get('largeScaleImageUrl') or ph.get('originalImageUrl'),
                'caption': (ph.get('description') or '').strip(),
            })

        apartments.append({
            'id': slug(list_name),
            'uid': o['uid'],
            'name': list_name,
            'code': code,
            'publicName': public_name,
            'residence': residence_for(list_name, addr.get('address2')),
            'street': (addr.get('address') or '').split(',')[-1].strip(),
            'address': addr.get('address'),
            'lat': addr.get('latitude'),
            'lng': addr.get('longitude'),
            'sizeM2': (p.get('area') or {}).get('size'),
            'bedrooms': p.get('bedrooms'),
            'beds': p.get('beds'),
            'bathrooms': int(float(p.get('bathrooms') or 0)),
            'maxGuests': avail.get('maxGuests'),
            'baseGuests': avail.get('baseGuests'),
            'minStay': avail.get('minimumStay'),
            'checkInFrom': avail.get('checkInTimeStart'),
            'checkOutBy': avail.get('checkOutTime'),
            'checkInMethod': checkin,
            'headline': parsed['headline'],
            'perfectFor': parsed['perfectFor'],
            'features': parsed['features'],
            'bedSpec': parsed['bedSpec'],
            'extras': parsed['extras'],
            'summary': (d.get('summary') or '').strip(),
            'amenities': amen_codes,
            'highlights': [c for c in HIGHLIGHT_AMENITIES if c in amen_codes],
            'isActive': p.get('isActive'),
            'publicListed': True,  # overwritten below
            'webLink': p.get('webLink'),
            'adminLink': f"https://platform.hostfully.com/app/#/property/{o['uid']}",
            'photos': photo_entries,
            'updated': p.get('updatedUtcDateTime'),
        })
    # A few units were geocoded badly in Hostfully (e.g. Cusco E19/F4 land 10 km
    # away). All units in a residence share a building, so snap every unit to
    # the residence's most common coordinate and keep the raw value for reference.
    from collections import Counter
    by_res = {}
    for a in apartments:
        if a['lat'] and a['lng']:
            by_res.setdefault(a['residence'], Counter())[(round(a['lat'], 5), round(a['lng'], 5))] += 1
    for a in apartments:
        if a['residence'] in by_res:
            (lat, lng), _ = by_res[a['residence']].most_common(1)[0]
            if (round(a['lat'] or 0, 5), round(a['lng'] or 0, 5)) != (lat, lng):
                a['rawLat'], a['rawLng'] = a['lat'], a['lng']
                a['geoSnapped'] = True
            a['lat'], a['lng'] = lat, lng

    apartments.sort(key=lambda a: (a['residence'], a['name']))
    return apartments


def download_images(apartments):
    jobs = []
    for a in apartments:
        for ph in a['photos']:
            dest = os.path.join(ROOT, ph['file'])
            if not os.path.exists(dest) and ph['url']:
                jobs.append((ph['url'], dest))

    def fetch(job):
        url, dest = job
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        # curl rather than urllib: the system python lacks the CA bundle for S3.
        r = subprocess.run(['curl', '-sSL', '--fail', '-o', dest, url], capture_output=True, text=True)
        if r.returncode != 0:
            print('FAILED', url, r.stderr.strip())
            return False
        return True

    print(f'downloading {len(jobs)} images...')
    with ThreadPoolExecutor(max_workers=12) as ex:
        ok = sum(ex.map(fetch, jobs))
    print(f'done: {ok}/{len(jobs)}')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    raw = json.load(open(sys.argv[1]))
    # The public booking site only lists a subset; mark which are visible there.
    public_uids = set()
    pub_path = os.path.join(os.path.dirname(sys.argv[1]), 'public_props.json')
    if os.path.exists(pub_path):
        public_uids = {p['uid'] for p in json.load(open(pub_path))['properties']}

    apartments = normalize(raw)
    for a in apartments:
        a['publicListed'] = a['uid'] in public_uids if public_uids else None
        hebrew.apply(a)
    for kind, text in sorted(hebrew.UNKNOWN):
        print(f'UNTRANSLATED {kind}: {text!r}')
    manual_path = os.path.join(DATA_DIR, 'manual.json')
    manual = json.load(open(manual_path, encoding='utf-8')) if os.path.exists(manual_path) else {}
    lo, hi = scoring.apply(apartments, manual)
    print(f'score tiers: yellow < {lo} <= orange < {hi} <= green')

    os.makedirs(DATA_DIR, exist_ok=True)
    out = os.path.join(DATA_DIR, 'apartments.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(apartments, f, ensure_ascii=False, indent=1)
    # The viewer is opened as a local file, so it can't fetch() JSON; ship it as JS too.
    with open(os.path.join(DATA_DIR, 'apartments.js'), 'w', encoding='utf-8') as f:
        f.write('window.APARTMENTS = ')
        json.dump(apartments, f, ensure_ascii=False)
        f.write(';\n')
    print(f'wrote {len(apartments)} apartments -> {out}')

    if '--skip-images' not in sys.argv:
        download_images(apartments)


if __name__ == '__main__':
    main()
