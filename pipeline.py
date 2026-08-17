#!/usr/bin/env python3
"""
311 Civic Pulse - data pipeline.
Downloads the City of Toronto 311 Service Requests datasets (current + previous
year), computes city/ward/category aggregates for the last 90 days, and writes
one JSON bundle + LLM-generated plain-language briefs for the static site.

Stdlib only. Key is read server-side from ~/dev/deepseek-harness/.env and is
never printed.
"""
import csv, io, json, os, re, sys, time, urllib.request, urllib.error, zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, 'data', 'raw')
OUT = os.path.join(BASE, 'data', 'out')
PKG = 'https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_show?id=311-service-requests-customer-initiated'
API_URL = 'https://api.deepseek.com/v1/chat/completions'
MODEL = 'deepseek-chat'
WINDOW_DAYS = 90

def log(msg):
    print(f'[{datetime.now().strftime("%H:%M:%S")}] {msg}', flush=True)

def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'civic-pulse/1.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def deepseek_key():
    p = os.path.expanduser('~/dev/deepseek-harness/.env')
    if not os.path.exists(p):
        return None
    m = re.search(r'^DEEPSEEK_API_KEY\s*=\s*["\']?([^"\'\s]+)', open(p).read(), re.M)
    return m.group(1) if m else None

def fetch_data():
    """Download current-year and previous-year zips if not already local."""
    os.makedirs(RAW, exist_ok=True)
    pkg = get_json(PKG)
    by_year = {}
    for r in pkg['result']['resources']:
        m = re.search(r'(20\d\d)', r['name'])
        if m and r.get('format') == 'ZIP':
            by_year[m.group(1)] = r
    year = datetime.now().year
    for y in (str(year), str(year - 1)):
        if y not in by_year:
            log(f'no {y} resource, skipping'); continue
        dest = os.path.join(RAW, f'SR{y}.csv')
        if os.path.exists(dest):
            log(f'{y} already local'); continue
        zip_path = os.path.join(RAW, f'sr{y}.zip')
        log(f'downloading {y} ({by_year[y].get("size", "?")} bytes)')
        req = urllib.request.Request(by_year[y]['url'], headers={'User-Agent': 'civic-pulse/1.0'})
        with urllib.request.urlopen(req, timeout=300) as r:
            open(zip_path, 'wb').write(r.read())
        with zipfile.ZipFile(zip_path) as z:
            name = next(n for n in z.namelist() if n.lower().endswith('.csv'))
            open(dest, 'wb').write(z.read(name))
        os.remove(zip_path)
        log(f'{y} extracted')

def load_rows(paths):
    rows = []
    for p in paths:
        if not os.path.exists(p):
            continue
        with open(p, encoding='latin-1', errors='replace') as f:
            rd = csv.DictReader(f)
            for row in rd:
                try:
                    dt = datetime.strptime(row['Creation Date'][:19], '%Y-%m-%d %H:%M:%S')
                except (ValueError, KeyError):
                    continue
                rows.append({
                    'dt': dt,
                    'status': (row.get('Status') or '').strip(),
                    'fsa': (row.get('First 3 Chars of Postal Code') or '').strip()[:3],
                    'ward': (row.get('Ward') or '').strip(),
                    'type': (row.get('Service Request Type') or '').strip(),
                    'div': (row.get('Division') or '').strip(),
                })
    return rows

def ward_num(ward):
    m = re.search(r'\((\d+)\)', ward)
    return int(m.group(1)) if m else 0

def agg(rows, now):
    """city + per-ward + per-category aggregates over the window."""
    window_start = now - timedelta(days=WINDOW_DAYS)
    prev_start = now - timedelta(days=2 * WINDOW_DAYS)
    in_win = [r for r in rows if r['dt'] >= window_start]
    in_prev = [r for r in rows if prev_start <= r['dt'] < window_start]

    def stats(sub):
        if not sub:
            return None
        done = sum(1 for r in sub if r['status'] == 'Completed')
        open_ = [r for r in sub if r['status'] != 'Completed']
        oldest = min(open_, key=lambda r: r['dt']) if open_ else None
        daily = defaultdict(int)
        for r in sub:
            daily[r['dt'].date().isoformat()] += 1
        days = sorted(daily)
        return {
            'count': len(sub),
            'completion_rate': round(100.0 * done / len(sub), 1),
            'open_count': len(open_),
            'oldest_open_days': (now - oldest['dt']).days if oldest else None,
            'oldest_open_type': oldest['type'] if oldest else None,
            'daily': [{'d': d, 'n': daily[d]} for d in days],
        }

    def top_types(sub, n=6):
        c = defaultdict(int)
        for r in sub:
            c[r['type']] += 1
        return [{'type': t, 'count': v} for t, v in sorted(c.items(), key=lambda x: -x[1])[:n]]

    city = {
        'now': now.isoformat(),
        'window_days': WINDOW_DAYS,
        'stats': stats(in_win),
        'prev_count': len(in_prev),
        'top_types': top_types(in_win, 14),
    }

    wards = defaultdict(list)
    for r in in_win:
        wards[r['ward'] or 'Unknown'].append(r)
    ward_out = []
    for w, sub in sorted(wards.items(), key=lambda kv: ward_num(kv[0])):
        prev = [r for r in in_prev if r['ward'] == w]
        ward_out.append({
            'ward': w,
            'stats': stats(sub),
            'prev_count': len(prev),
            'top_types': top_types(sub),
        })

    cats = defaultdict(list)
    for r in in_win:
        cats[r['type'] or 'Other'].append(r)
    cat_out = []
    for t, sub in cats.items():
        ward_c = defaultdict(int)
        for r in sub:
            ward_c[r['ward']] += 1
        cat_out.append({
            'type': t,
            'stats': stats(sub),
            'prev_count': len([r for r in in_prev if r['type'] == t]),
            'top_wards': [{'ward': w, 'count': c} for w, c in
                          sorted(ward_c.items(), key=lambda x: -x[1])[:4]],
            'division': sub[0]['div'],
        })
    cat_out.sort(key=lambda c: -(c['stats'] or {}).get('count', 0))
    cat_out = cat_out[:16]

    recent = sorted(in_win, key=lambda r: r['dt'], reverse=True)[:20]
    recent_out = [{
        'when': r['dt'].isoformat(timespec='minutes'),
        'status': r['status'], 'fsa': r['fsa'], 'ward': r['ward'],
        'type': r['type'],
    } for r in recent]

    return city, ward_out, cat_out, recent_out

def llm(prompt, key, max_tokens=240):
    body = json.dumps({
        'model': MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.3,
        'max_tokens': max_tokens,
    }).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.load(r)
            return d['choices'][0]['message']['content'].strip()
        except Exception as e:
            if attempt == 2:
                log(f'LLM fail ({type(e).__name__}): {e}')
                return None
            time.sleep(4 * (attempt + 1))

SYSTEM_RULES = ('Write like a sharp, plain-spoken city news brief. Facts only, no speculation, '
                'no filler, no bullet points, no markdown. Two or three sentences. Keep numbers exact.')

def make_briefs(city, wards, cats, key):
    def trend(cur, prev):
        if not prev:
            return 'no prior window'
        d = round(100.0 * (cur - prev) / prev, 1)
        return f'{d:+}% vs prior 90 days'

    briefs = {}
    s = city['stats']
    p = (f"City of Toronto 311, last {WINDOW_DAYS} days: {s['count']} requests, "
         f"{s['completion_rate']}% completed, {s['open_count']} open; oldest open is "
         f"{s['oldest_open_days']} days old ({s['oldest_open_type']}). "
         f"Trend: {trend(s['count'], city['prev_count'])}. "
         f"Top types: " + ', '.join(f"{t['type']} ({t['count']})" for t in city['top_types'][:5]) + '.')
    briefs['city'] = llm(f'{SYSTEM_RULES}\n\nData:\n{p}\n\nWrite the brief.', key)
    log('city brief done')

    for w in wards:
        s = w['stats']
        if not s:
            continue
        p = (f"Ward {w['ward']}, last {WINDOW_DAYS} days: {s['count']} requests, "
             f"{s['completion_rate']}% completed, {s['open_count']} open; oldest open is "
             f"{s['oldest_open_days']} days old ({s['oldest_open_type']}). "
             f"Trend: {trend(s['count'], w['prev_count'])}. "
             f"Top types: " + ', '.join(f"{t['type']} ({t['count']})" for t in w['top_types']) + '.')
        briefs[f"ward:{w['ward']}"] = llm(f'{SYSTEM_RULES}\n\nData:\n{p}\n\nWrite the brief.', key)
    log('ward briefs done')

    for c in cats[:10]:
        s = c['stats']
        if not s:
            continue
        p = (f"Toronto 311 category '{c['type']}', last {WINDOW_DAYS} days: {s['count']} requests, "
             f"{s['completion_rate']}% completed, {s['open_count']} open; oldest open is "
             f"{s['oldest_open_days']} days old. "
             f"Trend: {trend(s['count'], c['prev_count'])}. "
             f"Top wards: " + ', '.join(f"{t['ward']} ({t['count']})" for t in c['top_wards']) + '.')
        briefs[f"type:{c['type']}"] = llm(f'{SYSTEM_RULES}\n\nData:\n{p}\n\nWrite the brief.', key)
    log('category briefs done')
    return briefs

def main():
    os.makedirs(OUT, exist_ok=True)
    now = datetime.now()
    fetch_data()
    rows = load_rows([os.path.join(RAW, f'SR{now.year}.csv'),
                      os.path.join(RAW, f'SR{now.year - 1}.csv')])
    log(f'loaded {len(rows)} rows')
    city, wards, cats, recent = agg(rows, now)
    log(f'city={city["stats"]["count"]} requests/90d, wards={len(wards)}, cats={len(cats)}')

    key = deepseek_key()
    briefs = {}
    if key:
        briefs = make_briefs(city, wards, cats, key)
    else:
        log('no API key found - skipping LLM briefs')

    bundle = {
        'generated_at': now.isoformat(timespec='seconds'),
        'source': 'City of Toronto Open Data - 311 Service Requests (Customer Initiated)',
        'city': city, 'wards': wards, 'categories': cats, 'recent': recent,
        'briefs': briefs,
    }
    out_path = os.path.join(OUT, 'civic-pulse.json')
    json.dump(bundle, open(out_path, 'w'), indent=1)
    log(f'wrote {out_path} ({os.path.getsize(out_path)} bytes)')

if __name__ == '__main__':
    main()
