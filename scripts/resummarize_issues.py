#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
예전 코드로 만든 호(마크다운만 있는 호)의 요약을 현재 Gemini 파이프라인으로 다시 만듭니다.

- 대상: archives/ 의 최근 N개 호 (기본값: keywords.json 의 site_issue_count = 사이트에 보이는 호)
- 결과: archives/<호>.json 을 새로 씁니다. build_site.py 는 .json 이 있으면 그것을 우선 사용합니다.
- 원본 마크다운은 건드리지 않습니다 (기록 보존).
- 이미 .json 이 있는 호는 건너뜁니다. 다시 만들려면 --force.

사용 예:
    python scripts/resummarize_issues.py              # 최근 3개 호
    python scripts/resummarize_issues.py --issues 1   # 가장 최근 호만
    python scripts/resummarize_issues.py --dry-run    # 무엇을 할지만 출력
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site  # noqa: E402
import fetch_and_archive as fa  # noqa: E402  (.env 로드 · Gemini 호출 · 요약 캐시)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--issues", type=int, default=int(build_site.get_settings().get("site_issue_count", 3)))
    parser.add_argument("--force", action="store_true", help="이미 .json 이 있는 호도 다시 요약")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    md_files = sorted(fa.ARCHIVES_DIR.glob("*.md"), key=lambda p: p.name, reverse=True)[: args.issues]
    for md_path in md_files:
        json_path = md_path.with_suffix(".json")
        if json_path.exists() and not args.force:
            print(f"- {md_path.name}: 이미 JSON 있음 → 건너뜀 (--force 로 다시 만들기)")
            continue

        meta, body = build_site.parse_frontmatter(md_path.read_text(encoding="utf-8"))
        parsed = build_site.extract_articles_from_markdown(body)

        # 예전 코드는 가짜 초록("관련 학술 문헌 제목: …")이나 무관한 논문(효모·감자 육종 등)도 실었으므로
        # 현재 수집 기준(초록 검증 + 해조류 관련도)을 다시 적용합니다.
        articles = []
        for art in parsed:
            tier = fa.relevance_tier(art["title"], art.get("abstract", ""))
            if not fa.is_valid_abstract(art.get("abstract", "")) or tier is None:
                print(f"  - 제외: {art['title'][:60]}")
                continue
            art["tier"] = tier
            if tier == "related":
                art["category"] = "related_research"
                art["category_name"] = "연관 연구"
            articles.append(art)
        print(f"\n▶ {md_path.name}: {len(parsed)}편 중 {len(articles)}편 재요약"
              f"{' (dry-run)' if args.dry_run else ''}")
        if args.dry_run or not articles:
            continue

        ai_count = 0
        for idx, art in enumerate(articles, 1):
            lang = "ko" if fa._has_hangul(art["title"]) else "en"
            summary = fa.generate_natural_summary(
                title=art["title"],
                abstract=art.get("abstract", ""),
                category_name=art.get("category_name", ""),
                taxa_list=[t for t in art.get("taxa", []) if t and t != "Unclassified"],
                paper_lang=lang,
                doi=art.get("doi", ""),
            )
            if summary.get("is_ai"):
                ai_count += 1
                art["headline"] = summary["headline"]
                art["takeaways"] = summary["takeaways"]
                art["implications"] = summary["implications"]
            art["lang"] = lang
            art["is_ai_summary"] = bool(summary.get("is_ai"))
            art["summary_source"] = summary.get("summary_source", "markdown")
            print(f"  [{idx:02d}] {art['summary_source']:<16} {art['title'][:50]}")
            if summary.get("is_ai") and not summary.get("is_cached"):
                time.sleep(4.5)  # Gemini 무료 티어 분당 한도

        json_path.write_text(
            json.dumps({"date": meta.get("date", ""), "articles": articles, "resummarized": True},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  => {json_path.name} 저장 (AI 요약 {ai_count}/{len(articles)}편)")


if __name__ == "__main__":
    main()
