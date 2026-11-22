"""Add properties that exist in Hostfully but are NOT published to the booking site.

    python3 build/fetch_unpublished.py          # merges into build/raw/raw_all.json

For unpublished units the public API serves only the core record
(/api/public/properties/<uid>) — name, address, capacity, and the cover photo.
The gallery, description text and amenities live behind /api/public/dbs/* which
404s until the unit is published, so those records are marked `dataPartial`.

Publishing the unit in Hostfully is what makes the normal refresh pick it up in
full; this script just keeps it from being invisible in the meantime.

UIDS below comes from the Hostfully admin property list. Add or remove lines as
the inventory changes.
"""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

BASE = 'https://platform.hostfully.com/api/public'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'build', 'raw')

UIDS = """
Cusco D1|4e50b9cf-6dd5-4736-8f9b-57f3760eb1ec
Cusco D2|8df6bf21-2d15-4865-9e6b-62cb4630d868
Cusco E15|f106676d-1ba5-4c69-8107-ab1faacbec59
Cusco F3|1a7fb901-d96d-45e3-a741-86be71814f99
Cusco G19|eda81a28-2813-4473-9dcc-2b275955e1af
Cusco G20|a3a37c44-26e5-4d8d-bcad-5970c627f4d7
Cusco K14|1db260d7-f7be-40e2-8811-541534e209a2
Nazca C7|715da10d-9ee9-4432-8bba-9bebd35fd39e
"""


def get(url):
    r = subprocess.run(['curl', '-sS', '--fail', '--max-time', '60', url],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f'{url} -> {r.stderr.strip()}')
    return json.loads(r.stdout)


def one(entry):
    name, uid = entry
    p = get(f'{BASE}/properties/{uid}?locale=en_US')['property']
    cover = p.get('picture')
    return {
        'listName': name,
        'uid': uid,
        'dataPartial': True,
        'property': {
            'uid': uid,
            'name': p.get('name', name).strip(),
            'address': p.get('address'),
            'propertyType': p.get('propertyType'),
            'businessType': p.get('businessType'),
            'isActive': True,
            'pictureLink': cover,
            'webLink': p.get('webLink'),
            'bedrooms': p.get('bedrooms'),
            'beds': p.get('beds'),
            'bathrooms': p.get('bathrooms'),
            'area': None,          # not in the public record
            'availability': {
                'maxGuests': p.get('maxGuests'),
                'baseGuests': p.get('baseGuests'),
                'minimumStay': p.get('minStay'),
            },
            'cancellationPolicy': p.get('cancellationPolicy'),
        },
        # publicName carries the useful summary ("8 Guests Duplex (NZ-C7)")
        'descriptions': [{'name': p.get('publicName'), 'shortSummary': None,
                          'summary': None, 'locale': 'en_US'}],
        'photos': ([{'uid': 'cover', 'displayOrder': 0, 'description': None,
                     'mediumScaleImageUrl': cover, 'largeScaleImageUrl': cover,
                     'originalImageUrl': cover}] if cover else []),
        'amenities': [],
    }


def main():
    entries = [tuple(l.split('|')) for l in UIDS.strip().split('\n') if l.strip()]
    with ThreadPoolExecutor(max_workers=8) as ex:
        extra = list(ex.map(one, entries))

    path = os.path.join(RAW, 'raw_all.json')
    data = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else []
    have = {o['uid'] for o in data}
    added = [o for o in extra if o['uid'] not in have]
    data += added
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

    pub = os.path.join(RAW, 'public_props.json')
    if os.path.exists(pub):  # these are NOT on the public site — leave that list alone
        pass
    print(f'added {len(added)} unpublished properties (partial data); total {len(data)}')
    for o in added:
        a = o['property']
        print(f"  {o['listName']:12} {a['availability']['maxGuests']} guests, "
              f"{a['bedrooms']} bed, {'cover photo' if o['photos'] else 'NO photo'}")


if __name__ == '__main__':
    main()
