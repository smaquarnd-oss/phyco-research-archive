import json, sys, collections
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
with open('public/data/latest-articles.json', encoding='utf-8') as f:
    data = json.load(f)

arts = data['articles']
print(f'=== 총 {len(arts)}편 ===')

# 카테고리 분포
cats = collections.Counter(a['category'] for a in arts)
print('\n[카테고리 분포]')
for k, v in sorted(cats.items()):
    print(f'  {k}: {v}편')

# takeaway 중복 검사
print('\n[Takeaway 중복 검사]')
all_takes = []
for a in arts:
    all_takes.extend(a.get('takeaways', []))
dupe_takes = {t for t in all_takes if all_takes.count(t) > 1}
print(f'  전체 takeaway 수: {len(all_takes)}')
print(f'  중복 takeaway 수: {len(dupe_takes)}')
for d in list(dupe_takes)[:3]:
    print(f'  [중복] {d[:75]}')

# implications 중복 검사
print('\n[Researcher Takeaway(implications) 중복 검사]')
impls = [a.get('implications', '') for a in arts]
dupe_impls = {t for t in impls if impls.count(t) > 1 and t}
print(f'  전체: {len(impls)}건')
print(f'  중복: {len(dupe_impls)}건')
for d in list(dupe_impls)[:2]:
    print(f'  [중복] {d[:75]}')

# 샘플 3편 미리보기
print('\n[논문 샘플 3편 takeaway 미리보기]')
for a in arts[:3]:
    title = a['title']
    print(f'  제목: {title[:65]}')
    for t in a['takeaways']:
        print(f'    - {t[:85]}')
    print()
