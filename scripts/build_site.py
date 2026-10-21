#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phyco & Blue Carbon Magazine Static Site Builder v2.0
- 6개 섹션 체제 (SECTIONS 목록 참고): 01 육종·유전체·병해, 02 엽체 생리·생활사,
                   03 양식·배양 기술, 04 가공·소재·시장, 05 블루카본·메탄 저감·환경, 06 연관 연구
- 썸네일 키워드 기반 매칭 + 중복 없는 배정
- UI: 헤드라인, 3가지 Key Takeaways, 연구자 시사점, 토글형 초록
- Editor's Insight 섹션별 탑재
"""

import sys
import re
import html
import json
import os
import subprocess
from pathlib import Path

# Windows 콘솔 및 다국어 지원을 위한 UTF-8 강제 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import assign_unique_thumbnails, clean_summary  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
ARCHIVES_DIR = BASE_DIR / "archives"
PUBLIC_DIR = BASE_DIR / "public"
PUBLIC_DATA_DIR = PUBLIC_DIR / "data"

PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)

# 섹션 정의 (사이트의 메뉴·섹션 블록·JS 매핑이 모두 이 목록에서 만들어집니다)
# (카테고리 id, HTML slug, 번호, 아이콘, 국문명, 영문명, Tailwind 색, 메뉴 표기)
SECTIONS = [
    ("breeding_molecular_pathology",   "breeding",    "01", "🧬", "육종 · 유전체 · 병해",        "Breeding, Genomics & Disease",       "rose",    "육종·유전체·병해"),
    ("thallus_lifecycle_conchocelis",  "physiology",  "02", "🌱", "엽체 생리 · 생활사",          "Physiology & Life Cycle",            "emerald", "엽체 생리·생활사"),
    ("smart_aquaculture_mass_culture", "aquaculture", "03", "🏭", "양식 · 배양 기술",            "Cultivation & Farming",              "violet",  "양식·배양"),
    ("processing_materials_market",    "processing",  "04", "🏷️", "가공 · 소재 · 시장",          "Processing, Materials & Market",     "orange",  "가공·소재·시장"),
    ("blue_carbon_feed_methane",       "bluecarbon",  "05", "🌍", "블루카본 · 메탄 저감 · 환경", "Blue Carbon, Methane & Environment", "cyan",    "블루카본·메탄·환경"),
    ("related_research",               "related",     "06", "🔗", "연관 연구",                   "Related Research",                   "amber",   "연관 연구"),
]
SECTION_ORDER = [sec[0] for sec in SECTIONS]
CATEGORY_META = {
    sec[0]: {"no": sec[2], "icon": sec[3], "name_ko": sec[4], "name_en": sec[5], "color": sec[6]} for sec in SECTIONS
}
# 레거시 호환
CATEGORY_META["thallus_lifecycle_cultivation"] = dict(CATEGORY_META["thallus_lifecycle_conchocelis"])


def render_nav_html() -> str:
    links = []
    for cat, slug, no, icon, _ko, _en, c, short in SECTIONS:
        links.append(
            f'          <a href="#sec-{slug}" id="nav-{slug}" class="px-3 py-1 rounded-md bg-{c}-50 text-{c}-800 '
            f'dark:bg-{c}-950/60 dark:text-{c}-300 hover:bg-{c}-100 font-medium transition flex items-center gap-1 '
            f'border border-{c}-200 dark:border-{c}-800">\n            <span>{icon} {no}. {short}</span>\n          </a>'
        )
    return "\n".join(links)


def render_sections_html() -> str:
    blocks = []
    for cat, slug, no, icon, ko, en, c, _short in SECTIONS:
        label = "Editor's Note" if cat == "related_research" else "Editor's Insight"
        blocks.append(f"""    <!-- ========== SECTION {no}: {ko} ========== -->
    <section id="sec-{slug}" class="scroll-mt-32">
      <div class="flex flex-col sm:flex-row sm:items-end justify-between border-b-2 border-{c}-500 pb-3 mb-6">
        <div>
          <span class="text-xs font-black tracking-widest text-{c}-600 dark:text-{c}-400 uppercase">SECTION {no}</span>
          <h2 class="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white flex items-center gap-2">
            <span>{icon} {ko}</span>
            <span class="text-sm font-normal text-slate-400">({html.escape(en)})</span>
          </h2>
        </div>
        <span id="badge-count-{slug}" class="text-xs font-semibold px-2.5 py-1 rounded-full bg-{c}-100 text-{c}-800 dark:bg-{c}-950 dark:text-{c}-300 w-fit mt-2 sm:mt-0">0편 수록</span>
      </div>
      <div class="rounded-2xl bg-gradient-to-r from-{c}-500/10 via-{c}-500/5 to-transparent border border-{c}-200 dark:border-{c}-900/60 p-5 mb-8 shadow-sm">
        <div class="flex items-center gap-2 text-{c}-800 dark:text-{c}-300 font-bold text-sm mb-2">
          <i data-lucide="feather" class="w-4 h-4 text-{c}-600"></i>
          <span>{label}: <span id="insight-title-{slug}" class="font-extrabold"></span></span>
        </div>
        <p id="insight-content-{slug}" class="text-xs sm:text-sm text-slate-700 dark:text-slate-300 leading-relaxed"></p>
      </div>
      <div id="grid-{slug}" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"><!-- JS 주입 --></div>
    </section>
""")
    return "\n".join(blocks)


def parse_frontmatter(content):
    """마크다운 파일 상단의 YAML Frontmatter를 파싱합니다."""
    meta = {}
    body = content
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if match:
        yaml_text = match.group(1)
        body = match.group(2)
        for line in yaml_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if v.startswith("[") and v.endswith("]"):
                    try:
                        meta[k] = json.loads(v)
                    except:
                        meta[k] = [x.strip().strip('"').strip("'") for x in v[1:-1].split(",") if x.strip()]
                elif v.isdigit():
                    meta[k] = int(v)
                else:
                    meta[k] = v
    return meta, body


def detect_category_from_header(header: str) -> str | None:
    """섹션 헤더 문자열로 카테고리 ID를 감지합니다."""
    h = header.lower()
    if "연관 연구" in h or "related research" in h:
        return "related_research"
    if "가공" in h or "소재" in h or "시장" in h or "processing" in h:
        return "processing_materials_market"
    if "육종" in h or "breeding" in h or "분자" in h or "병해" in h:
        return "breeding_molecular_pathology"
    if "스마트 양식" in h or "대량 배양" in h or "배양 기술" in h or "mass culture" in h or "aquaculture" in h or "cultivation" in h or "채묘" in h:
        return "smart_aquaculture_mass_culture"
    if "엽체" in h or "생활사" in h or "사상체" in h or "thallus" in h or "conchocel" in h:
        return "thallus_lifecycle_conchocelis"
    if "블루카본" in h or "blue carbon" in h or "사료" in h or "메탄" in h or "산업" in h:
        return "blue_carbon_feed_methane"
    return None


def extract_articles_from_markdown(body: str) -> list:
    """마크다운 본문에서 논문 섹션들을 구조화된 객체로 추출합니다."""
    articles = []
    current_category = "thallus_lifecycle_conchocelis"
    current_cat_name = "엽체 생리 · 생활사 · 사상체"

    sections = body.split("\n## ")
    for sec in sections:
        lines = sec.splitlines()
        header = lines[0] if lines else ""

        # 카테고리 헤더 감지
        detected = detect_category_from_header(header)
        if detected:
            current_category = detected
            meta = CATEGORY_META.get(current_category, {})
            current_cat_name = meta.get("name_ko", current_category)

        # 각 논문 (### 로 시작하는 블록) 파싱
        subsections = ("\n" + sec).split("\n### ")
        for sub in subsections[1:]:
            sub_lines = sub.strip().splitlines()
            if not sub_lines:
                continue
            headline = sub_lines[0].strip()
            headline = re.sub(r"^\d+\.\s*", "", headline)
            sub_text = "\n".join(sub_lines[1:])

            # 원문 제목
            title = headline
            m_title = re.search(r"-\s*\*\*원문 제목\*\*:\s*([^\n]+)", sub_text)
            if m_title:
                title = m_title.group(1).strip()

            # 저자
            authors = "연구진 미상"
            m_auth = re.search(r"-\s*\*\*저자\*\*:\s*([^\n|]+)", sub_text)
            if m_auth:
                authors = m_auth.group(1).strip()

            # 저널
            journal = "Academic Journal"
            m_jour = re.search(r"-\s*\*\*저널\*\*:\s*([^\n|]+)", sub_text)
            if m_jour:
                journal = m_jour.group(1).strip().replace("*", "")

            # 출처: "🇰🇷 국내 KCI" / "🌐 해외 PubMed"
            source, is_domestic = "", False
            m_src = re.search(r"\*\*출처\*\*:\s*(🇰🇷\s*국내|🌐\s*해외)?\s*([^|\n]+)", sub_text)
            if m_src:
                is_domestic = bool(m_src.group(1) and "국내" in m_src.group(1))
                source = m_src.group(2).strip()

            year = ""
            m_year = re.search(r"\((\d{4})\)", journal)
            if m_year:
                year = m_year.group(1)
                journal = journal[:m_year.start()].strip()

            # DOI URL
            doi_url = "#"
            doi = ""
            m_doi = re.search(r"-\s*\*\*.*?\*\*:\s*.*?\[(.*?)\]\((.*?)\)", sub_text)
            if m_doi:
                doi_url = m_doi.group(2).strip()
                if m_doi.group(1).startswith("10."):
                    doi = m_doi.group(1).strip()
            else:
                m_link = re.search(r"https?://[^\s\)]+", sub_text)
                if m_link:
                    doi_url = m_link.group(0)

            # 생물군
            taxa = []
            m_taxa = re.search(r"-\s*\*\*대상 생물군\*\*:\s*`([^`]+)`", sub_text)
            if m_taxa:
                taxa = [t.strip() for t in m_taxa.group(1).split(",")]
            else:
                for tax_name in ["Neopyropia", "Pyropia", "Porphyra", "Neoporphyra", "Phycocalidia", "Asparagopsis"]:
                    if tax_name.lower() in sub.lower():
                        taxa.append(tax_name)
                if not taxa:
                    taxa = ["Pyropia"]

            # 썸네일 (마크다운에 명시된 것 우선, 없으면 카테고리별 풀에서 중복 없이 배정)
            thumbnail_url = ""
            m_thumb = re.search(r"-\s*\*\*대표 이미지\*\*:\s*!\[.*?\]\((.*?)\)", sub_text)
            if m_thumb:
                thumbnail_url = m_thumb.group(1).strip()

            # 3가지 핵심 요약 포인트
            takeaways = []
            # 헤더 문구가 버전마다 달라("3가지 핵심 요약" / "핵심 요약 포인트") 이모지로만 찾습니다.
            m_takeaways = re.search(r"####\s*📌[^\n]*\n(.*?)(?=\n####|\n---|\Z)", sub_text, re.DOTALL)
            if m_takeaways:
                raw_t = m_takeaways.group(1).strip()
                for line in raw_t.splitlines():
                    clean_line = re.sub(r"^\d+\.\s*", "", line).strip()
                    if clean_line:
                        takeaways.append(clean_line)

            # 연구자 시사점
            implications = ""
            m_imp = re.search(r"####\s*💡[^\n]*\n(.*?)(?=\n####|\n---|\Z)", sub_text, re.DOTALL)
            if m_imp:
                implications = m_imp.group(1).strip()

            # 원문 초록
            abstract_text = ""
            m_abs = re.search(r"####\s*📄[^\n]*\n(.*?)(?=\n####|\n---|\Z)", sub_text, re.DOTALL)
            if m_abs:
                abstract_text = m_abs.group(1).strip()

            # 중복 제거 · 템플릿 제거 · 부족하면 초록에서 추출 (시사점은 없으면 비워서 카드에서 숨김)
            takeaways, implications = clean_summary(takeaways, implications, abstract_text)
            if not takeaways:
                takeaways = [title]

            articles.append({
                "headline": headline,
                "title": title,
                "authors": authors,
                "journal": journal,
                "url": doi_url,
                "doi": doi,
                "year": year,
                "taxa": taxa,
                "category": current_category,
                "category_name": current_cat_name,
                "thumbnail_url": thumbnail_url,
                "takeaways": takeaways,
                "implications": implications,
                "abstract": abstract_text,
                "source": source,
                "is_domestic": is_domestic,
            })

    return articles


def get_settings() -> dict:
    try:
        return json.loads((BASE_DIR / "keywords.json").read_text(encoding="utf-8")).get("search_settings", {})
    except (OSError, json.JSONDecodeError):
        return {}


def get_repo_url() -> str:
    """GitHub 저장소 주소. Actions 에서는 GITHUB_REPOSITORY, 로컬에서는 git remote 에서 읽습니다."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        try:
            remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=BASE_DIR,
                                    capture_output=True, text=True, timeout=10).stdout.strip()
            m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", remote)
            repo = m.group(1) if m else ""
        except (OSError, subprocess.SubprocessError):
            repo = ""
    return f"https://github.com/{repo}" if repo else ""


def build_site():
    """모든 마크다운 아카이브를 스캔하여 정적 사이트를 빌드합니다."""
    print("==================================================")
    print("🚀 Phyco Research Magazine Web Builder v2.0 (4-section)")
    print("==================================================")

    md_files = sorted(list(ARCHIVES_DIR.glob("*.md")), reverse=True)
    if not md_files:
        print("[-] 빌드할 아카이브 파일(*.md)이 없습니다.")
        return

    # 사이트에는 최근 N개 호만 싣습니다 (index.html 크기 고정). 이전 호는 GitHub archives/ 에 그대로 남습니다.
    site_issue_count = int(get_settings().get("site_issue_count", 3))
    md_files.sort(key=lambda p: p.name, reverse=True)

    archives_index = []

    for md_path in md_files:
        if len(archives_index) >= site_issue_count:
            break
        content = md_path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)

        # fetch_and_archive.py 가 함께 저장한 JSON 이 있으면 그대로 사용 (마크다운 재파싱 손실 없음)
        json_path = md_path.with_suffix(".json")
        editor_insights = {}
        if json_path.exists():
            issue_data = json.loads(json_path.read_text(encoding="utf-8"))
            articles = issue_data.get("articles", [])
            # 섹션별 Editor's Insight: 그 호 논문으로 생성된 것만 사용 (없으면 사이트에서 상자를 숨김)
            editor_insights = issue_data.get("editor_insights") or {}
            for art in articles:
                art["takeaways"], art["implications"] = clean_summary(
                    art.get("takeaways", []), art.get("implications", ""), art.get("abstract", "")
                )
        else:
            articles = extract_articles_from_markdown(body)

        # 한 호 안에서 같은 사진이 두 번 나오지 않게 (카테고리를 넘어서도)
        assign_unique_thumbnails(articles)

        file_date = meta.get("date")
        if not file_date:
            m_date = re.search(r"\d{4}-\d{2}-\d{2}", md_path.name)
            file_date = m_date.group(0) if m_date else "2026-10-07"

        if not articles:
            print(f"  - {md_path.name}: 논문 0편 → 건너뜀")
            continue

        # frontmatter 가 없는 옛 형식은 첫 번째 "# 제목" 줄을 씁니다.
        m_h1 = re.search(r"^#\s+(?:🌊\s*)?(.+)$", body, re.MULTILINE)
        title = meta.get("title") or (m_h1.group(1).strip() if m_h1 else f"연구 격주 다이제스트 ({file_date})")
        archive_entry = {
            "filename": md_path.name,
            "title": title,
            "date": file_date,
            "total_papers": len(articles) if articles else meta.get("total_papers", 0),
            "taxa_covered": meta.get("taxa_covered", ["Pyropia", "Asparagopsis"]),
            "categories": meta.get("categories", []),
            "editor_insights": editor_insights,
            "articles": articles
        }
        archives_index.append(archive_entry)

    # 날짜 기준 최신순. 첫 화면은 논문이 있는 가장 최근 호.
    archives_index.sort(key=lambda a: a["date"], reverse=True)
    if not archives_index:
        print("[-] 논문이 있는 호가 없어 빌드를 건너뜁니다.")
        return
    latest_archive = archives_index[0]
    older_count = len(md_files) - len(archives_index)

    with open(PUBLIC_DATA_DIR / "archives-index.json", "w", encoding="utf-8") as f:
        json.dump(archives_index, f, ensure_ascii=False, indent=2)
    print(f" => 사이트 수록: 최근 {len(archives_index)}개 호 {[a['date'] for a in archives_index]} "
          f"(그 밖의 {max(older_count, 0)}개 호는 GitHub archives/ 에만 보관)")

    html_content = generate_magazine_html(latest_archive, archives_index, get_repo_url())
    index_file = PUBLIC_DIR / "index.html"
    index_file.write_text(html_content, encoding="utf-8")
    print(f" => 학술 매거진 빌드 완료: {index_file}")


def generate_magazine_html(latest_archive, archives_index, repo_url=""):
    """
    전문 학술 매거진 스타일 싱글 페이지 정적 HTML 템플릿을 생성합니다.
    주의: Python f-string이므로 JS 중괄호는 모두 {{ }} 로 이스케이프.
    """
    index_json_str = json.dumps(archives_index, ensure_ascii=False).replace("</", r"<\/")
    nav_html = render_nav_html()
    sections_html = render_sections_html()
    sections_json = json.dumps([{"cat": sec[0], "slug": sec[1]} for sec in SECTIONS], ensure_ascii=False)
    repo_href = html.escape(repo_url or "https://github.com", quote=True)
    archives_href = html.escape(f"{repo_url}/tree/main/archives" if repo_url else "https://github.com", quote=True)

    return f"""<!DOCTYPE html>
<html lang="ko" class="scroll-smooth">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>김/바다고리풀속 &amp; 블루카본 연구 매거진 | Phyco &amp; Blue Carbon Biweekly</title>
  <meta name="description" content="김(Pyropia/Porphyra), 바다고리풀(Asparagopsis), 블루카본 및 메탄저감 해조류 연구 자동화 학술 매거진">

  <!-- Favicon SVG -->
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🌊</text></svg>">

  <!-- Tailwind CSS CDN -->
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {{
      darkMode: 'class',
      theme: {{
        extend: {{
          colors: {{
            ocean: {{
              50: '#f0fdfa', 100: '#ccfbf1', 200: '#99f6e4', 300: '#5eead4',
              400: '#2dd4bf', 500: '#14b8a6', 600: '#0d9488', 700: '#0f766e',
              800: '#115e59', 900: '#134e4a', 950: '#042f2e',
            }},
            deepsea: {{ 800: '#0b192c', 900: '#051120', 950: '#020914' }}
          }},
          fontFamily: {{
            sans: ['Pretendard', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
            serif: ['Newsreader', 'Georgia', 'serif'],
          }}
        }}
      }}
    }}
  </script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600;1,6..72,400&display=swap" rel="stylesheet">
  <link rel="stylesheet" as="style" crossorigin href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" />
  <script src="https://unpkg.com/lucide@latest"></script>
  <style>
    body {{ font-family: 'Pretendard', sans-serif; }}
    .font-serif-mag {{ font-family: 'Newsreader', Georgia, serif; }}
    .glass-panel {{
      background: rgba(255, 255, 255, 0.9);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
    }}
    .dark .glass-panel {{
      background: rgba(11, 25, 44, 0.9);
    }}
    .gradient-hero {{
      background: radial-gradient(circle at 10% 20%, rgba(13,148,136,.15) 0%, transparent 40%),
                  radial-gradient(circle at 90% 80%, rgba(6,182,212,.12) 0%, transparent 40%);
    }}
  </style>
</head>
<body class="bg-slate-100/60 dark:bg-deepsea-950 text-slate-800 dark:text-slate-100 min-h-screen transition-colors duration-200">

  <!-- 상단 글로벌 네비게이션 -->
  <header class="sticky top-0 z-40 glass-panel border-b border-slate-200/80 dark:border-slate-800 transition-colors">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <span class="text-2xl animate-pulse">🌊</span>
        <div>
          <a href="#" class="font-black text-lg text-ocean-900 dark:text-ocean-200 tracking-tight flex items-center gap-2">
            PHYCO &amp; BLUE CARBON
            <span class="text-[11px] px-2 py-0.5 rounded-full bg-ocean-100 text-ocean-800 dark:bg-ocean-950 dark:text-ocean-300 font-bold border border-ocean-300 dark:border-ocean-700">Research Magazine</span>
          </a>
          <p class="text-[11px] text-slate-500 dark:text-slate-400 hidden sm:block">홍조류 신분류체계 생물학 · 스마트 양식 · 해양 탄소격리 전문 격주간지</p>
        </div>
      </div>

      <div class="flex items-center space-x-3">
        <button id="archive-modal-btn" class="text-xs sm:text-sm px-3.5 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 flex items-center gap-1.5 transition">
          <i data-lucide="archive" class="w-4 h-4 text-ocean-600"></i>
          <span>지난 호수 열람</span>
          <span id="archive-count-badge" class="ml-1 text-[11px] px-1.5 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 font-bold">1</span>
        </button>
        <button id="theme-toggle" class="p-2 rounded-lg text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800 transition" title="다크 모드 전환">
          <i data-lucide="moon" class="w-5 h-5 hidden dark:block"></i>
          <i data-lucide="sun" class="w-5 h-5 block dark:hidden"></i>
        </button>
      </div>
    </div>

    <!-- 섹션 바로가기 네비게이터 -->
    <div class="border-t border-slate-200/60 dark:border-slate-800/80 bg-white/70 dark:bg-deepsea-900/70 backdrop-blur-md">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2 flex items-center justify-between text-xs overflow-x-auto gap-4">
        <span class="text-slate-400 font-semibold uppercase tracking-wider shrink-0 flex items-center gap-1">
          <i data-lucide="compass" class="w-3.5 h-3.5"></i> 섹션:
        </span>
        <div class="flex items-center space-x-2 shrink-0">
{nav_html}
        </div>
      </div>
    </div>
  </header>

  <!-- 매거진 메인 히어로 배너 -->
  <section class="gradient-hero border-b border-slate-200/80 dark:border-slate-800/80 py-10 sm:py-16">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="max-w-3xl">
        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-ocean-100/90 dark:bg-ocean-950/90 border border-ocean-300 dark:border-ocean-800 text-ocean-900 dark:text-ocean-300 text-xs font-bold mb-4">
          <i data-lucide="book-open" class="w-3.5 h-3.5"></i>
          <span>BIWEEKLY RESEARCH MAGAZINE</span>
          <span class="mx-1">•</span>
          <span id="hero-issue-date">2026-10-07호</span>
        </div>
        <h1 class="text-3xl sm:text-5xl font-black tracking-tight text-slate-900 dark:text-white leading-tight">
          해조류 오믹스부터<br class="hidden sm:inline" />
          <span class="text-transparent bg-clip-text bg-gradient-to-r from-ocean-600 via-teal-500 to-cyan-500 dark:from-ocean-400 dark:via-teal-300 dark:to-cyan-300">
            해양 탄소격리 기후테크
          </span>까지
        </h1>
        <p class="mt-4 text-base sm:text-lg text-slate-600 dark:text-slate-300 leading-relaxed">
          <em>Pyropia</em>, <em>Porphyra</em>, <em>Neopyropia</em>, <em>Neoporphyra</em>, <em>Phycocalidia</em> 및 <em>Asparagopsis</em>의
          최신 학술 논문을 5개 전문 섹션과 연관 연구로 엄선하여 핵심 요약, 시사점, 에디터 트렌드 브리핑과 함께 제공합니다.
        </p>
        <div class="mt-6 flex flex-wrap gap-4 pt-2">
          <div class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            <span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
            이번 호 분석 논문: <strong id="stat-papers" class="text-slate-900 dark:text-white">-편</strong>
          </div>
          <div class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            <span class="w-2.5 h-2.5 rounded-full bg-ocean-500"></span>
            포함 생물군: <strong id="stat-taxa" class="text-slate-900 dark:text-white">6개 속</strong>
          </div>
          <div class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            <span class="w-2.5 h-2.5 rounded-full bg-cyan-500"></span>
            발행 주기: <strong class="text-slate-900 dark:text-white">격주 수요일 정기 발행</strong>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- 실시간 검색 및 생물군 필터 바 -->
  <section class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 -mt-6">
    <div class="glass-panel p-4 sm:p-5 rounded-2xl shadow-xl border border-slate-200/90 dark:border-slate-800/90 space-y-3">
      <div class="flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div class="relative w-full sm:max-w-md">
          <i data-lucide="search" class="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2"></i>
          <input type="text" id="search-input" placeholder="헤드라인, 저자, 초록, 키워드 실시간 검색..."
            class="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-deepsea-900 text-sm focus:outline-none focus:ring-2 focus:ring-ocean-500 transition" />
        </div>
        <div class="flex items-center gap-3 w-full sm:w-auto justify-end">
          <span class="text-xs text-slate-500 dark:text-slate-400">검색 매칭: <strong id="filter-count" class="text-ocean-600 dark:text-ocean-400 font-bold">-</strong>건</span>
          <button id="reset-filters" class="text-xs px-2.5 py-1.5 text-slate-500 hover:text-slate-800 dark:hover:text-white transition underline">필터 초기화</button>
        </div>
      </div>
      <div class="flex items-center gap-1.5 flex-wrap pt-2 border-t border-slate-100 dark:border-slate-800/60 text-xs">
        <span class="text-slate-400 text-[11px] font-semibold mr-1 flex items-center gap-1">
          <i data-lucide="tag" class="w-3 h-3"></i> 생물군 필터:
        </span>
        <button data-taxa="all" class="taxa-btn px-2.5 py-1 rounded-md text-[11px] font-bold bg-slate-300 dark:bg-slate-700 text-slate-900 dark:text-slate-100">전체보기</button>
        <button data-taxa="Pyropia" class="taxa-btn px-2.5 py-1 rounded-md text-[11px] font-medium bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 border border-slate-200 dark:border-slate-700">Pyropia (김속)</button>
        <button data-taxa="Porphyra" class="taxa-btn px-2.5 py-1 rounded-md text-[11px] font-medium bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 border border-slate-200 dark:border-slate-700">Porphyra (원형 김)</button>
        <button data-taxa="Neopyropia" class="taxa-btn px-2.5 py-1 rounded-md text-[11px] font-medium bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 border border-slate-200 dark:border-slate-700">Neopyropia (방사무늬김)</button>
        <button data-taxa="Neoporphyra" class="taxa-btn px-2.5 py-1 rounded-md text-[11px] font-medium bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 border border-slate-200 dark:border-slate-700">Neoporphyra (모무늬돌김)</button>
        <button data-taxa="Phycocalidia" class="taxa-btn px-2.5 py-1 rounded-md text-[11px] font-medium bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 border border-slate-200 dark:border-slate-700">Phycocalidia</button>
        <button data-taxa="Asparagopsis" class="taxa-btn px-2.5 py-1 rounded-md text-[11px] font-medium bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 border border-slate-200 dark:border-slate-700">Asparagopsis (바다고리풀)</button>
      </div>
    </div>
  </section>

  <!-- 매거진 본문: 4대 카테고리별 섹션 구역 분리 -->
  <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-16">

{sections_html}
    <!-- 검색 결과 없음 -->
    <div id="empty-state" class="hidden text-center py-20 bg-white dark:bg-deepsea-900 rounded-2xl border border-slate-200 dark:border-slate-800">
      <i data-lucide="file-search" class="w-14 h-14 mx-auto text-slate-300 dark:text-slate-600 mb-3"></i>
      <h3 class="text-lg font-bold text-slate-800 dark:text-slate-200">일치하는 연구 논문이 없습니다</h3>
      <p class="text-xs text-slate-500 mt-1">다른 검색어나 생물군 태그(전체보기)를 선택해 보세요.</p>
    </div>

  </main>

  <!-- 플로팅 맨 위로 -->
  <a href="#" class="fixed bottom-6 right-6 z-40 p-3 rounded-full bg-ocean-600 text-white shadow-lg hover:bg-ocean-700 transition flex items-center justify-center" title="맨 위로">
    <i data-lucide="arrow-up" class="w-5 h-5"></i>
  </a>

  <!-- 지난 아카이브 모달 -->
  <div id="archive-modal" class="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm hidden flex items-center justify-center p-4">
    <div class="glass-panel w-full max-w-xl rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-2xl space-y-4 max-h-[85vh] flex flex-col">
      <div class="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
        <div class="flex items-center gap-2">
          <i data-lucide="archive" class="w-5 h-5 text-ocean-600"></i>
          <h2 class="text-lg font-bold text-slate-900 dark:text-white">지난 호수 목록</h2>
        </div>
        <button id="close-modal" class="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
          <i data-lucide="x" class="w-5 h-5"></i>
        </button>
      </div>
      <p class="text-xs text-slate-500">사이트에는 최근 {len(archives_index)}개 호만 싣습니다. 이전 호는 아래 GitHub 아카이브에서 마크다운으로 볼 수 있습니다.</p>
      <div id="archive-list" class="space-y-2 overflow-y-auto pr-1 flex-1"><!-- JS 동적 생성 --></div>
      <div class="pt-3 border-t border-slate-200 dark:border-slate-800 text-xs text-slate-400">
        <a href="{archives_href}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 font-bold text-ocean-600 dark:text-ocean-400 hover:underline">
          <i data-lucide="github" class="w-3.5 h-3.5"></i> 전체 아카이브 보기 (GitHub archives/) →
        </a>
      </div>
    </div>
  </div>

  <!-- 푸터 -->
  <footer class="mt-20 border-t border-slate-200 dark:border-slate-800 py-12 bg-white/70 dark:bg-deepsea-900/70">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-6 text-xs text-slate-500 dark:text-slate-400">
      <div>
        <p class="font-bold text-sm text-slate-800 dark:text-slate-200">PHYCO &amp; BLUE CARBON RESEARCH MAGAZINE v2.0</p>
        <p class="mt-1">Automated Research Pipeline powered by GitHub Actions &amp; Vercel Global Edge</p>
        <p class="mt-0.5 text-slate-400 text-[11px]">Target Genera: Pyropia, Porphyra, Neopyropia, Neoporphyra, Phycocalidia, Asparagopsis</p>
        <p class="mt-0.5 text-slate-400 text-[11px]">5+1 Sections: Breeding · Physiology · Cultivation · Processing &amp; Market · Blue Carbon · Related Research</p>
      </div>
      <div class="flex items-center space-x-4">
        <a href="{repo_href}" target="_blank" rel="noopener noreferrer" class="hover:text-ocean-600 dark:hover:text-ocean-400 transition flex items-center gap-1 font-medium">
          <i data-lucide="github" class="w-4 h-4"></i> GitHub Repository
        </a>
        <span>•</span>
        <span>Biweekly (Wed) Auto-Update</span>
      </div>
    </div>
  </footer>

  <!-- 클라이언트 로직 및 데이터 주입 -->
  <script>
    const ALL_ARCHIVES = {index_json_str};
    const INITIAL_ARCHIVE = ALL_ARCHIVES[0];  // 최신 호 (중복으로 넣지 않음)

    let currentArchive = INITIAL_ARCHIVE;
    let selectedTaxa = 'all';
    let searchQuery = '';

    function esc(v) {{
      return String(v ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    }}
    function safeUrl(u) {{
      return /^https?:[/][/]/i.test(u || '') ? esc(u) : '#';
    }}

    function initIcons() {{
      if (window.lucide) lucide.createIcons();
    }}

    // 다크모드 초기화
    const themeToggleBtn = document.getElementById('theme-toggle');
    if (localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {{
      document.documentElement.classList.add('dark');
    }} else {{
      document.documentElement.classList.remove('dark');
    }}
    themeToggleBtn.addEventListener('click', () => {{
      document.documentElement.classList.toggle('dark');
      localStorage.theme = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
      initIcons();
    }});

    // 논문 카드 렌더러
    function renderCard(art, idx) {{
      const taxaBadges = (art.taxa || []).filter(t => t && t !== 'Unclassified' && t !== '-').map(t =>
        `<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-black/60 backdrop-blur-md text-white border border-white/20 italic">${{esc(t)}}</span>`
      ).join(' ');

      const extraBadges =
        (art.tier === 'related' ? `<span class="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-400/90 text-amber-950 border border-amber-200/60">연관 연구</span>` : '') +
        (art.is_domestic ? `<span class="px-2 py-0.5 rounded text-[11px] font-bold bg-white/90 text-slate-800 border border-white/40">🇰🇷 국내</span>` : '');

      const takeawaysList = (art.takeaways || []).map((point, pIdx) => `
        <li class="flex items-start gap-2 text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
          <span class="shrink-0 w-4 h-4 rounded-full bg-ocean-100 dark:bg-ocean-950 text-ocean-700 dark:text-ocean-300 flex items-center justify-center text-[10px] font-bold mt-0.5 border border-ocean-300 dark:border-ocean-800">${{pIdx + 1}}</span>
          <span>${{esc(point)}}</span>
        </li>
      `).join('');

      const cleanAbstract = (art.abstract || '초록 정보가 제공되지 않는 논문입니다.').replaceAll('###','').replaceAll('####','').replaceAll('**','').trim();

      return `
        <article class="flex flex-col justify-between rounded-2xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-deepsea-900 shadow-sm hover:shadow-xl hover:border-ocean-300 dark:hover:border-ocean-600 transition-all duration-300 overflow-hidden group">
          <div>
            <!-- 썸네일 -->
            <div class="relative h-48 w-full overflow-hidden bg-slate-100 dark:bg-slate-800">
              <img src="${{safeUrl(art.thumbnail_url)}}" alt="${{esc(art.headline)}}"
                class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500 ease-out"
                loading="lazy" />
              <div class="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent"></div>
              <div class="absolute top-3 left-3 flex flex-wrap gap-1">${{extraBadges}}${{taxaBadges}}</div>
              <div class="absolute top-3 right-3">
                <span class="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-white/90 dark:bg-black/80 backdrop-blur-md text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-700">
                  ${{esc(art.journal || 'Journal')}}
                </span>
              </div>
              <div class="absolute bottom-2.5 left-3 right-3 text-[11px] text-white/90 truncate">
                <i data-lucide="user" class="w-3 h-3 inline mr-1 text-ocean-300"></i> ${{esc(art.authors || 'Authors')}}
              </div>
            </div>

            <!-- 카드 본문 -->
            <div class="p-5 sm:p-6 space-y-4">
              <!-- 헤드라인 -->
              <h3 class="text-base sm:text-lg font-bold text-slate-900 dark:text-white group-hover:text-ocean-600 dark:group-hover:text-ocean-400 transition-colors leading-snug line-clamp-2">
                <a href="${{safeUrl(art.url)}}" target="_blank" rel="noopener noreferrer">${{esc(art.headline)}}</a>
              </h3>
              <!-- 원문 제목 -->
              <p class="text-xs text-slate-500 dark:text-slate-400 line-clamp-2 font-mono">${{esc(art.title)}}</p>

              <!-- Key Takeaways -->
              <div class="pt-3 border-t border-slate-100 dark:border-slate-800/80">
                <h4 class="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider mb-2.5 flex items-center gap-1.5">
                  <i data-lucide="check-circle-2" class="w-3.5 h-3.5 text-emerald-500"></i>
                  <span>Key Takeaways (핵심 성과)</span>
                </h4>
                <ul class="space-y-2">${{takeawaysList}}</ul>
              </div>

              <!-- 연구자 시사점 -->
              ${{art.implications ? `
                <div class="p-3 rounded-xl bg-ocean-50/80 dark:bg-ocean-950/50 border border-ocean-200/80 dark:border-ocean-900/60">
                  <h5 class="text-[11px] font-bold text-ocean-800 dark:text-ocean-300 uppercase tracking-wider mb-1 flex items-center gap-1">
                    <i data-lucide="lightbulb" class="w-3 h-3 text-amber-500"></i>
                    <span>Researcher's Takeaway (시사점)</span>
                  </h5>
                  <p class="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">${{esc(art.implications)}}</p>
                </div>
              ` : ''}}

              <!-- 초록 토글 -->
              <div class="pt-2">
                <button type="button" onclick="toggleAbstractView('${{idx}}')" id="btn-abstract-${{idx}}"
                  class="text-xs font-bold text-slate-600 dark:text-slate-300 hover:text-ocean-600 dark:hover:text-ocean-400 transition flex items-center gap-1.5 py-1 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 hover:border-ocean-300">
                  <i data-lucide="file-text" class="w-3.5 h-3.5"></i>
                  <span>초록 원문 보기</span>
                  <i data-lucide="chevron-down" id="icon-abstract-${{idx}}" class="w-3.5 h-3.5 transition-transform duration-200"></i>
                </button>
                <div id="abstract-drawer-${{idx}}" class="hidden mt-3 p-4 rounded-xl bg-slate-50 dark:bg-deepsea-950 border border-slate-200 dark:border-slate-800 text-xs font-serif-mag text-slate-700 dark:text-slate-300 leading-relaxed max-h-80 overflow-y-auto whitespace-pre-line shadow-inner">
                  <div class="text-[10px] font-mono uppercase tracking-wider text-slate-400 mb-1.5 font-sans font-bold flex items-center justify-between">
                    <span>ORIGINAL ABSTRACT</span>
                    <span>DOI: ${{esc(art.doi || '-')}}</span>
                  </div>
                  ${{esc(cleanAbstract)}}
                </div>
              </div>
            </div>
          </div>

          <!-- 카드 푸터 -->
          <div class="px-5 sm:px-6 py-3 border-t border-slate-100 dark:border-slate-800/80 bg-slate-50/50 dark:bg-deepsea-900/50 flex items-center justify-between">
            <span class="text-[11px] text-slate-400">${{esc(art.journal || 'Academic Article')}}${{art.year ? ' (' + esc(art.year) + ')' : ''}}</span>
            <a href="${{safeUrl(art.url)}}" target="_blank" rel="noopener noreferrer"
              class="inline-flex items-center gap-1.5 text-xs font-bold text-ocean-600 dark:text-ocean-400 hover:text-ocean-800 dark:hover:text-ocean-300 transition">
              <span>원문 열람 (DOI)</span>
              <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
            </a>
          </div>
        </article>
      `;
    }}

    // ──────────────────────────────────────────────────────────────
    // 섹션 렌더링
    // ──────────────────────────────────────────────────────────────
    function renderSections() {{
      const allArticles = currentArchive.articles || [];
      const emptyState = document.getElementById('empty-state');
      const filterCount = document.getElementById('filter-count');

      // 필터 적용
      const filtered = allArticles.filter(art => {{
        if (selectedTaxa !== 'all') {{
          const hasTaxa = (art.taxa || []).some(t => t.toLowerCase().includes(selectedTaxa.toLowerCase()));
          const matchTitle = (art.title || '').toLowerCase().includes(selectedTaxa.toLowerCase());
          const matchHead = (art.headline || '').toLowerCase().includes(selectedTaxa.toLowerCase());
          if (!hasTaxa && !matchTitle && !matchHead) return false;
        }}
        if (searchQuery.trim() !== '') {{
          const q = searchQuery.toLowerCase();
          const texts = [art.headline, art.title, art.authors, art.abstract, ...(art.takeaways || [])].join(' ').toLowerCase();
          if (!texts.includes(q)) return false;
        }}
        return true;
      }});

      filterCount.innerText = filtered.length;

      // 섹션 목록 (build_site.py 의 SECTIONS 에서 생성)
      const SECTIONS = {sections_json};
      const LEGACY_MAP = {{ 'thallus_lifecycle_cultivation': 'thallus_lifecycle_conchocelis' }};

      const groups = {{}};
      SECTIONS.forEach(sec => groups[sec.cat] = []);
      filtered.forEach((art, idx) => {{
        let cat = LEGACY_MAP[art.category] || art.category;
        if (!groups[cat]) cat = 'related_research';
        groups[cat].push({{ art, globalIdx: idx }});
      }});

      const insights = currentArchive.editor_insights || {{}};
      SECTIONS.forEach(({{cat, slug}}) => {{
        const items = groups[cat];
        document.getElementById('grid-' + slug).innerHTML = items.map(item => renderCard(item.art, item.globalIdx)).join('');
        document.getElementById('badge-count-' + slug).innerText = `${{items.length}}편 수록`;
        // 논문이 없는 섹션은 본문·메뉴 모두 숨김
        document.getElementById('sec-' + slug).classList.toggle('hidden', items.length === 0);
        document.getElementById('nav-' + slug).classList.toggle('hidden', items.length === 0);

        // Editor's Insight: 그 호 논문으로 만든 것만, 없으면 상자 숨김
        const ins = insights[cat];
        const tEl = document.getElementById('insight-title-' + slug);
        const cEl = document.getElementById('insight-content-' + slug);
        tEl.closest('.rounded-2xl').classList.toggle('hidden', !(ins && ins.content));
        tEl.innerText = (ins && ins.title) || '';
        cEl.innerText = (ins && ins.content) || '';
      }});

      emptyState.classList.toggle('hidden', filtered.length > 0);
      initIcons();
    }}

    // 초록 토글
    window.toggleAbstractView = function(idx) {{
      const drawer = document.getElementById(`abstract-drawer-${{idx}}`);
      const btn = document.getElementById(`btn-abstract-${{idx}}`);
      const icon = document.getElementById(`icon-abstract-${{idx}}`);
      if (!drawer || !btn) return;
      const isHidden = drawer.classList.contains('hidden');
      if (isHidden) {{
        drawer.classList.remove('hidden');
        btn.querySelector('span').innerText = '초록 원문 숨기기';
        btn.classList.add('bg-ocean-50', 'text-ocean-700', 'border-ocean-300');
        if (icon) icon.classList.add('rotate-180');
      }} else {{
        drawer.classList.add('hidden');
        btn.querySelector('span').innerText = '초록 원문 보기';
        btn.classList.remove('bg-ocean-50', 'text-ocean-700', 'border-ocean-300');
        if (icon) icon.classList.remove('rotate-180');
      }}
      initIcons();
    }};

    // 검색
    document.getElementById('search-input').addEventListener('input', (e) => {{
      searchQuery = e.target.value;
      renderSections();
    }});

    // 생물군 필터
    document.querySelectorAll('.taxa-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.taxa-btn').forEach(b => {{
          b.className = 'taxa-btn px-2.5 py-1 rounded-md text-[11px] font-medium bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 border border-slate-200 dark:border-slate-700';
        }});
        btn.className = 'taxa-btn px-2.5 py-1 rounded-md text-[11px] font-bold bg-slate-300 dark:bg-slate-700 text-slate-900 dark:text-slate-100';
        selectedTaxa = btn.getAttribute('data-taxa');
        renderSections();
      }});
    }});

    // 필터 초기화
    document.getElementById('reset-filters').addEventListener('click', () => {{
      selectedTaxa = 'all';
      searchQuery = '';
      document.getElementById('search-input').value = '';
      document.querySelector('.taxa-btn[data-taxa="all"]').click();
    }});

    // 지난 호수 모달
    const modal = document.getElementById('archive-modal');
    const modalBtn = document.getElementById('archive-modal-btn');
    const closeModal = document.getElementById('close-modal');
    const archiveList = document.getElementById('archive-list');
    const archiveCountBadge = document.getElementById('archive-count-badge');

    archiveCountBadge.innerText = ALL_ARCHIVES.length;

    modalBtn.addEventListener('click', () => {{
      archiveList.innerHTML = ALL_ARCHIVES.map(arch => `
        <div class="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 hover:bg-ocean-50/60 dark:hover:bg-slate-800/60 transition cursor-pointer flex items-center justify-between"
             onclick="switchArchive('${{arch.date}}')">
          <div>
            <h4 class="text-sm font-bold text-slate-800 dark:text-slate-200">${{esc(arch.title)}}</h4>
            <p class="text-xs text-slate-400 mt-0.5">발행일: ${{arch.date}} • 분석 논문: ${{arch.total_papers || (arch.articles || []).length}}편</p>
          </div>
          <span class="text-xs font-bold text-ocean-600 dark:text-ocean-400 flex items-center gap-1">
            호수 열람 <i data-lucide="chevron-right" class="w-3.5 h-3.5"></i>
          </span>
        </div>
      `).join('');
      modal.classList.remove('hidden');
      initIcons();
    }});

    closeModal.addEventListener('click', () => modal.classList.add('hidden'));
    modal.addEventListener('click', (e) => {{ if (e.target === modal) modal.classList.add('hidden'); }});

    window.switchArchive = function(date) {{
      const found = ALL_ARCHIVES.find(a => a.date === date);
      if (found) {{
        currentArchive = found;
        document.getElementById('hero-issue-date').innerText = found.date + '호';
        document.getElementById('stat-papers').innerText = (found.articles || []).length + '편';
        renderSections();
        modal.classList.add('hidden');
      }}
    }};

    // 초기 렌더링
    document.getElementById('hero-issue-date').innerText = currentArchive.date + '호';
    document.getElementById('stat-papers').innerText = (currentArchive.articles || []).length + '편';
    renderSections();
    initIcons();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    build_site()
