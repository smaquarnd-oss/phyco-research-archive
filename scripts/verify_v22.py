import json
import sys
import collections

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
with open('public/data/latest-articles.json', encoding='utf-8') as f:
    data = json.load(f)

arts = data['articles']
print(f"=== 총 {len(arts)}편 논문 검증 ===")

# 소스별 수량
src_cnt = collections.Counter(a['source'] for a in arts)
print("\n[데이터 소스별 분포]")
for k, v in src_cnt.items():
    print(f"  {k}: {v}편")

# 카테고리별 분포
cat_cnt = collections.Counter(a['category'] for a in arts)
print("\n[카테고리별 분포]")
for k, v in cat_cnt.items():
    print(f"  {k}: {v}편")

# 템플릿 접두사 검사
all_takes = [t for a in arts for t in a.get('takeaways', [])]
template_take_prefixes = [t for t in all_takes if any(t.startswith(p) for p in ['연구 목적:', '주요 성과:', '시사점:', '결론:'])]
print("\n[템플릿 접두사 검사]")
print(f"  접두사(연구 목적:, 주요 성과: 등) 잔존 수: {len(template_take_prefixes)}건")

impls = [a.get('implications', '') for a in arts]
bad_impl_templates = [i for i in impls if '기초 생물학적 근거 및 실용화 가이드라인' in i or '환경 최적화 및 실용화 타당성을 검증' in i]
print(f"  구형 템플릿 시사점 잔존 수: {len(bad_impl_templates)}건")

# 썸네일 고유성 검사
thumbs = [a.get('thumbnail_url', '') for a in arts]
unique_thumbs = set(thumbs)
print("\n[썸네일 고유성 검사]")
print(f"  총 썸네일 수: {len(thumbs)}")
print(f"  완전 고유 썸네일 수: {len(unique_thumbs)}")
print(f"  중복 발생 여부: {len(thumbs) != len(unique_thumbs)}")

# 국내 논문(KCI) 3편 샘플 출력
print("\n[국내 KCI 논문 샘플 3편의 Takeaways & Implications]")
kci_samples = [a for a in arts if a['source'] == 'KCI'][:3]
for idx, p in enumerate(kci_samples, 1):
    title = p['title']
    print(f"\n--- [국내 KCI 논문 {idx}] ---")
    print(f"  제목: {title}")
    print(f"  섹션: {p['category_name']}")
    print(f"  썸네일 URL: {p['thumbnail_url'][:80]}...")
    print("  Key Takeaways:")
    for t in p['takeaways']:
        print(f"    • {t}")
    print(f"  Researcher's Takeaway: {p['implications']}")
