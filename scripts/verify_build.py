import json, sys
from collections import Counter
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
with open('public/data/latest-articles.json', encoding='utf-8') as f:
    data = json.load(f)
total = data['total_papers']
articles = data['articles']
cats = Counter(a['category'] for a in articles)
print(f'Total papers: {total}')
for k, v in sorted(cats.items()):
    print(f'  {k}: {v} papers')
thumbs = [a['thumbnail_url'] for a in articles]
dupe_urls = {t for t in set(thumbs) if thumbs.count(t) > 1}
print(f'Duplicate thumbnails (across ALL papers): {len(dupe_urls)} URL(s) reused')
for d in dupe_urls:
    print(f'  - {d[:80]}')
cat_thumbs = {}
for a in articles:
    cat_thumbs.setdefault(a['category'], []).append(a['thumbnail_url'])
print()
for cat, tlist in cat_thumbs.items():
    dupe_in_cat = {t for t in set(tlist) if tlist.count(t) > 1}
    print(f'{cat}: {len(tlist)} papers, {len(dupe_in_cat)} intra-cat duplicates')
