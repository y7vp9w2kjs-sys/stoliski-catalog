"""Pull the whole catalog from Hostfully's PUBLIC API — no login, no browser.

    python3 build/fetch_public.py            # -> build/raw/raw_all.json
    python3 build/fetch_public.py --quiet

Every StoliSki property is published on the public booking site, so the public
endpoints serve the same photos, descriptions and amenities the admin UI shows.
That makes a refresh a single command instead of a browser session.

The public API never exposes key-box codes or wifi, so nothing has to be stripped.
"""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

AGENCY = 'c3fc415b-c6b6-4268-b638-82ba8b5432f3'
BASE = 'https://platform.hostfully.com/api/public'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'build', 'raw')


def get(url):
    r = subprocess.run(['curl', '-sS', '--fail', '--max-time', '60', url],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f'{url} -> {r.stderr.strip()}')
    return json.loads(r.stdout)


def fetch_all(quiet=False):
    props = []
    offset = 0
    while True:  # public list caps at 50 per page
        page = get(f'{BASE}/properties?agencyUid={AGENCY}&_limit=50&_offset={offset}&locale=en_US')
        props += page['properties']
        if not page.get('_metadata', {}).get('hasNextPage'):
            break
        offset += 50
    if not quiet:
        print(f'{len(props)} properties listed')

    def one(p):
        uid = p['uid']
        q = f'propertyUid={uid}&locale=en_US'
        photos = get(f'{BASE}/dbs/photos?{q}').get('photos', [])
        descs = get(f'{BASE}/dbs/descriptions?{q}').get('descriptions', [])
        amens = get(f'{BASE}/dbs/amenities?{q}').get('amenities', [])
        return {
            'listName': p['name'].strip(),
            'uid': uid,
            # shape this like the admin export so build_data.py needs no changes
            'property': {
                'uid': uid,
                'name': p['name'].strip(),
                'address': p.get('address'),
                'propertyType': p.get('propertyType'),
                'businessType': p.get('businessType'),
                'isActive': True,
                'pictureLink': p.get('picture'),
                'webLink': p.get('webLink'),
                'bedrooms': p.get('bedrooms'),
                'beds': p.get('beds'),
                'bathrooms': p.get('bathrooms'),
                'area': p.get('area'),
                'availability': {
                    'maxGuests': p.get('maxGuests'),
                    'baseGuests': p.get('baseGuests'),
                    'minimumStay': p.get('minStay'),
                    'checkInTimeStart': p.get('checkInTimeStart'),
                    'checkOutTime': p.get('checkOutTime'),
                },
                'cancellationPolicy': p.get('cancellationPolicy'),
            },
            'descriptions': descs,
            'photos': photos,
            'amenities': amens,
        }

    with ThreadPoolExecutor(max_workers=8) as ex:
        out = list(ex.map(one, props))
    if not quiet:
        print(f'{sum(len(o["photos"]) for o in out)} photos, '
              f'{sum(len(o["amenities"]) for o in out)} amenities')
    return out


def main():
    quiet = '--quiet' in sys.argv
    data = fetch_all(quiet)
    os.makedirs(RAW, exist_ok=True)
    path = os.path.join(RAW, 'raw_all.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    # build_data.py reads this to mark which units are on the public site
    with open(os.path.join(RAW, 'public_props.json'), 'w', encoding='utf-8') as f:
        json.dump({'properties': [{'uid': o['uid'], 'name': o['listName']} for o in data]}, f,
                  ensure_ascii=False)
    if not quiet:
        print(f'wrote {path}')


if __name__ == '__main__':
    main()
