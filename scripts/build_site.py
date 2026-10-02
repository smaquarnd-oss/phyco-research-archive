#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phyco & Blue Carbon Magazine Static Site Builder
- 전문 학술 매거진 스타일 전면 리디자인:
  1. UI/UX: 직관적 한 줄 헤드라인, 3가지 핵심 요약(Key Takeaways), 연구자 시사점, 토글형 초록 전문
  2. 카테고리별 섹션 완벽 분리 및 'Editor's Weekly Insight' 트렌드 브리핑 탑재
  3. 대표 해양/사이언스 고해상도 썸네일 이미지 매칭
"""

import os
import sys
import re
import json
from pathlib import Path
from datetime import datetime

# Windows 콘솔 및 다국어 지원을 위한 UTF-8 강제 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).resolve().parent.parent
ARCHIVES_DIR = BASE_DIR / "archives"
PUBLIC_DIR = BASE_DIR / "public"
PUBLIC_DATA_DIR = PUBLIC_DIR / "data"

PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)

CURATED_THUMBNAILS = {
    "breeding_molecular_pathology": [
        "https://images.unsplash.com/photo-1532187863486-abf9dbad1b69?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1579154204601-01588f351e67?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1507668077129-56e32842fceb?auto=format&fit=crop&w=800&q=80"
    ],
    "thallus_lifecycle_cultivation": [
        "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1518837695005-2083093ee35b?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1581093458791-9f3c3900df4b?auto=format&fit=crop&w=800&q=80"
    ],
    "blue_carbon_feed_methane": [
        "https://images.unsplash.com/photo-1682687220063-4742bd7fd538?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1682687220199-d0124f48f95b?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1500595046743-cd271d694d30?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1498084393753-b411b2d26b34?auto=format&fit=crop&w=800&q=80"
    ]
}

DEFAULT_INSIGHTS = {
    "breeding_molecular_pathology": {
        "title": "기후 온난화 대응 내열성 분자마커와 붉은갯병 감염 초기 전사체 분석의 고도화",
        "content": "이번 주 육종 및 병해 연구 트렌드는 해수 온도 상승에 따른 내삼투압/열충격 단백질(HSP) 발현 메커니즘 규명과 더불어, 주요 병원체(Pythium porphyrae)에 대응하는 방어 전사인자(bZIP, MYB) 동정이 두드러집니다. 다중 오믹스 분석을 통한 유용 유전자원 선발이 양식장 현장 품종 개량의 핵심 열쇠로 자리잡고 있습니다."
    },
    "thallus_lifecycle_cultivation": {
        "title": "패각 대체 스마트 사상체 배양과 인산·질소 영양염 대사 적응 전략",
        "content": "엽체 생리 및 양식 기술 분야에서는 기존 굴패각 배양의 한계를 뛰어넘는 액체 통기 자유사상체 배양 조건과 연안 영양염(N, P) 결핍에 대응하는 periplasmic alkaline phosphatase 등의 효소 기전이 집중 조명되었습니다. 스마트 육상 채묘 및 환경 제어형 시스템의 경제성 확보가 핵심 과제로 부각되고 있습니다."
    },
    "blue_carbon_feed_methane": {
        "title": "바다고리풀 브로모포름 메탄 감축 실증과 해양 블루카본 탄소 격리 플럭스 표준화",
        "content": "블루카본 및 사료 분야는 Asparagopsis taxiformis의 장기 급여를 통한 반추위 장내 메탄 70~80% 억제 효과와 조직 내 브로모포름 잔류 안전성 검증이 핵심 성과로 보고되었습니다. 아울러 대형 홍조류의 연간 침적 유기탄소(POC/DOC)를 탄소배출권(mCDR)으로 공인받기 위한 정량적 방법론 연구가 급물살을 타고 있습니다."
    }
}


def parse_frontmatter(content):
    """마크다운 파일 상단의 YAML Frontmatter를 파싱합니다."""
    meta = {}
    body = content
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
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


def extract_articles_from_markdown(body):
    """마크다운 본문에서 논문 섹션들을 구조화된 객체로 추출합니다."""
    articles = []
    current_category = "thallus_lifecycle_cultivation"
    current_cat_name = "엽체 · 생활사 · 양식·배양"

    sections = body.split("\n## ")
    for sec in sections:
        lines = sec.splitlines()
        header = lines[0] if lines else ""
        
        # 카테고리 헤더 감지
        if "육종" in header or "Breeding" in header:
            current_category = "breeding_molecular_pathology"
            current_cat_name = "육종 · 분자생물학 · 병해"
        elif "엽체" in header or "Thallus" in header:
            current_category = "thallus_lifecycle_cultivation"
            current_cat_name = "엽체 · 생활사 · 양식·배양"
        elif "블루카본" in header or "Blue Carbon" in header or "사료" in header:
            current_category = "blue_carbon_feed_methane"
            current_cat_name = "블루카본 · 저메탄 사료 · 기후대응"

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

            # DOI URL
            doi_url = "#"
            m_doi = re.search(r"-\s*\*\*.*?\*\*:\s*.*?\[(.*?)\]\((.*?)\)", sub_text)
            if m_doi:
                doi_url = m_doi.group(2).strip()
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

            # 썸네일
            thumbnail_url = ""
            m_thumb = re.search(r"-\s*\*\*대표 이미지\*\*:\s*!\[.*?\]\((.*?)\)", sub_text)
            if m_thumb:
                thumbnail_url = m_thumb.group(1).strip()
            if not thumbnail_url:
                thumbs = CURATED_THUMBNAILS.get(current_category, CURATED_THUMBNAILS["thallus_lifecycle_cultivation"])
                thumbnail_url = thumbs[len(articles) % len(thumbs)]

            # 3가지 핵심 요약 포인트 (Key Takeaways)
            takeaways = []
            m_takeaways = re.search(r"####\s*📌\s*3가지 핵심 요약.*?\n(.*?)(?=\n####|\n---|\Z)", sub_text, re.DOTALL)
            if m_takeaways:
                raw_t = m_takeaways.group(1).strip()
                for line in raw_t.splitlines():
                    clean_line = re.sub(r"^\d+\.\s*", "", line).strip()
                    if clean_line:
                        takeaways.append(clean_line)

            # 연구자 시사점 (Researcher's Takeaway)
            implications = ""
            m_imp = re.search(r"####\s*💡\s*연구자 시사점.*?\n(.*?)(?=\n####|\n---|\Z)", sub_text, re.DOTALL)
            if m_imp:
                implications = m_imp.group(1).strip()

            # 원문 초록 (Abstract)
            abstract_text = ""
            m_abs = re.search(r"####\s*📄\s*논문 원문 초록.*?\n(.*?)(?=\n####|\n---|\Z)", sub_text, re.DOTALL)
            if m_abs:
                abstract_text = m_abs.group(1).strip()
            else:
                # 이전 포맷 폴백
                m_abs_old = re.search(r"####\s*(?:📄|📌)\s*.*?(?:Abstract|초록).*?\n(.*?)(?=\n####|\n---|\Z)", sub_text, re.DOTALL)
                if m_abs_old:
                    abstract_text = m_abs_old.group(1).strip()

            # 이전 아카이브 호환용 Takeaways 보정
            if not takeaways:
                if abstract_text:
                    sentences = [s.strip() for s in re.split(r"\.\s+", abstract_text) if len(s.strip()) > 15]
                    if len(sentences) >= 3:
                        takeaways = [f"연구 목적: {sentences[0]}.", f"주요 발견: {sentences[1]}.", f"결론 및 성과: {sentences[-1]}."]
                    elif len(sentences) == 2:
                        takeaways = [f"연구 배경: {sentences[0]}.", f"주요 성과: {sentences[1]}.", f"생물군 {', '.join(taxa)}의 환경 적응 분석."]
                    else:
                        takeaways = [f"{', '.join(taxa)} 대상 {current_cat_name} 분석 수행.", f"학술 논문 DOI를 통해 상세 프로토콜 제공."]
                else:
                    takeaways = [f"{', '.join(taxa)} 관련 {current_cat_name} 최신 성과.", "정규 색인 학술지 논문."]

            if not implications:
                implications = f"본 연구는 {', '.join(taxa)}의 {current_cat_name} 전략 수립 및 관련 산업화 연구에 기초 학술적 근거를 제공합니다."

            articles.append({
                "headline": headline,
                "title": title,
                "authors": authors,
                "journal": journal,
                "url": doi_url,
                "taxa": taxa,
                "category": current_category,
                "category_name": current_cat_name,
                "thumbnail_url": thumbnail_url,
                "takeaways": takeaways,
                "implications": implications,
                "abstract": abstract_text
            })

    return articles


def build_site():
    """모든 마크다운 아카이브를 스캔하여 정적 사이트를 빌드합니다."""
    print("==================================================")
    print("🚀 Phyco Research Magazine Web Builder")
    print("==================================================")

    md_files = sorted(list(ARCHIVES_DIR.glob("*.md")), reverse=True)
    if not md_files:
        print("[-] 빌드할 아카이브 파일(*.md)이 없습니다.")
        return

    archives_index = []
    latest_archive = None

    for md_path in md_files:
        content = md_path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)
        articles = extract_articles_from_markdown(body)
        
        file_date = meta.get("date")
        if not file_date:
            m_date = re.search(r"\d{4}-\d{2}-\d{2}", md_path.name)
            file_date = m_date.group(0) if m_date else "2026-10-02"

        title = meta.get("title", f"연구 주간 다이제스트 ({file_date})")
        archive_entry = {
            "filename": md_path.name,
            "title": title,
            "date": file_date,
            "total_papers": len(articles) if articles else meta.get("total_papers", 0),
            "taxa_covered": meta.get("taxa_covered", ["Pyropia", "Asparagopsis"]),
            "categories": meta.get("categories", []),
            "editor_insights": DEFAULT_INSIGHTS,
            "articles": articles
        }
        archives_index.append(archive_entry)
        
        if latest_archive is None:
            latest_archive = archive_entry

    # archives-index.json 저장
    with open(PUBLIC_DATA_DIR / "archives-index.json", "w", encoding="utf-8") as f:
        json.dump(archives_index, f, ensure_ascii=False, indent=2)
    print(f" => 아카이브 색인 생성 완료 ({len(archives_index)}개 아카이브)")

    # index.html 템플릿 생성
    html_content = generate_magazine_html(latest_archive, archives_index)
    index_file = PUBLIC_DIR / "index.html"
    index_file.write_text(html_content, encoding="utf-8")
    print(f" => 모던 학술 매거진 빌드 완료: {index_file}")


def generate_magazine_html(latest_archive, archives_index):
    """
    전문 학술 매거진 스타일 싱글 페이지 정적 HTML 템플릿을 생성합니다.
    - 카테고리별 섹션 분리 및 Editor's Weekly Insight
    - 논문 카드: 직관적 헤드라인, 3가지 Key Takeaways, 시사점, 토글형 초록
    - 고해상도 사이언스 썸네일 이미지 매칭
    """
    latest_json_str = json.dumps(latest_archive, ensure_ascii=False)
    index_json_str = json.dumps(archives_index, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ko" class="scroll-smooth">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>김/바다고리풀속 & 블루카본 연구 매거진 | Phyco & Blue Carbon Weekly</title>
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
              50: '#f0fdfa',
              100: '#ccfbf1',
              200: '#99f6e4',
              300: '#5eead4',
              400: '#2dd4bf',
              500: '#14b8a6',
              600: '#0d9488',
              700: '#0f766e',
              800: '#115e59',
              900: '#134e4a',
              950: '#042f2e',
            }},
            deepsea: {{
              800: '#0b192c',
              900: '#051120',
              950: '#020914',
            }}
          }},
          fontFamily: {{
            sans: ['Pretendard', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
            serif: ['Newsreader', 'Georgia', 'serif'],
          }}
        }}
      }}
    }}
  </script>
  <!-- Google Fonts: Newsreader (매거진 본문용) & Pretendard -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600;1,6..72,400&display=swap" rel="stylesheet">
  <link rel="stylesheet" as="style" crossorigin href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" />
  
  <!-- Lucide Icons -->
  <script src="https://unpkg.com/lucide@latest"></script>
  <style>
    body {{
      font-family: 'Pretendard', sans-serif;
    }}
    .font-serif-mag {{
      font-family: 'Newsreader', Georgia, serif;
    }}
    .glass-panel {{
      background: rgba(255, 255, 255, 0.9);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
    }}
    .dark .glass-panel {{
      background: rgba(11, 25, 44, 0.9);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
    }}
    .gradient-hero {{
      background: radial-gradient(circle at 10% 20%, rgba(13, 148, 136, 0.15) 0%, transparent 40%),
                  radial-gradient(circle at 90% 80%, rgba(6, 182, 212, 0.12) 0%, transparent 40%);
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
            PHYCO & BLUE CARBON
            <span class="text-[11px] px-2 py-0.5 rounded-full bg-ocean-100 text-ocean-800 dark:bg-ocean-950 dark:text-ocean-300 font-bold border border-ocean-300 dark:border-ocean-700">Research Magazine</span>
          </a>
          <p class="text-[11px] text-slate-500 dark:text-slate-400 hidden sm:block">홍조류 신분류체계 생물학 · 스마트 양식 · 해양 탄소격리 전문 주간지</p>
        </div>
      </div>

      <div class="flex items-center space-x-3">
        <button id="archive-modal-btn" class="text-xs sm:text-sm px-3.5 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 flex items-center gap-1.5 transition">
          <i data-lucide="archive" class="w-4 h-4 text-ocean-600"></i>
          <span>지난 호수 열람</span>
          <span id="archive-count-badge" class="ml-1 text-[11px] px-1.5 py-0.2 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 font-bold">1</span>
        </button>

        <button id="theme-toggle" class="p-2 rounded-lg text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800 transition" title="다크 모드 전환">
          <i data-lucide="moon" class="w-5 h-5 hidden dark:block"></i>
          <i data-lucide="sun" class="w-5 h-5 block dark:hidden"></i>
        </button>
      </div>
    </div>

    <!-- 스티키 섹션 바로가기 네비게이터 -->
    <div class="border-t border-slate-200/60 dark:border-slate-800/80 bg-white/70 dark:bg-deepsea-900/70 backdrop-blur-md">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2 flex items-center justify-between text-xs overflow-x-auto gap-4">
        <span class="text-slate-400 font-semibold uppercase tracking-wider shrink-0 flex items-center gap-1">
          <i data-lucide="compass" class="w-3.5 h-3.5"></i> 섹션 바로가기:
        </span>
        <div class="flex items-center space-x-2 shrink-0">
          <a href="#sec-breeding" class="px-3 py-1 rounded-md bg-rose-50 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300 hover:bg-rose-100 font-medium transition flex items-center gap-1.5 border border-rose-200 dark:border-rose-800">
            <span>🧬 01. 육종 · 분자 · 병해</span>
          </a>
          <a href="#sec-cultivation" class="px-3 py-1 rounded-md bg-emerald-50 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 hover:bg-emerald-100 font-medium transition flex items-center gap-1.5 border border-emerald-200 dark:border-emerald-800">
            <span>🌱 02. 엽체 · 생활사 · 배양</span>
          </a>
          <a href="#sec-bluecarbon" class="px-3 py-1 rounded-md bg-cyan-50 text-cyan-800 dark:bg-cyan-950/60 dark:text-cyan-300 hover:bg-cyan-100 font-medium transition flex items-center gap-1.5 border border-cyan-200 dark:border-cyan-800">
            <span>🌍 03. 블루카본 · 저메탄 사료</span>
          </a>
        </div>
      </div>
    </div>
  </header>

  <!-- 메거진 메인 히어로 배너 -->
  <section class="gradient-hero border-b border-slate-200/80 dark:border-slate-800/80 py-10 sm:py-16">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="max-w-3xl">
        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-ocean-100/90 dark:bg-ocean-950/90 border border-ocean-300 dark:border-ocean-800 text-ocean-900 dark:text-ocean-300 text-xs font-bold mb-4">
          <i data-lucide="book-open" class="w-3.5 h-3.5"></i>
          <span>WEEKLY RESEARCH MAGAZINE</span>
          <span class="mx-1">•</span>
          <span id="hero-issue-date">2026-10-02호</span>
        </div>
        <h1 class="text-3xl sm:text-5xl font-black tracking-tight text-slate-900 dark:text-white leading-tight">
          해조류 오믹스부터<br class="hidden sm:inline" />
          <span class="text-transparent bg-clip-text bg-gradient-to-r from-ocean-600 via-teal-500 to-cyan-500 dark:from-ocean-400 dark:via-teal-300 dark:to-cyan-300">
            해양 탄소격리 기후테크
          </span>까지
        </h1>
        <p class="mt-4 text-base sm:text-lg text-slate-600 dark:text-slate-300 leading-relaxed">
          *Pyropia*, *Porphyra*, *Neopyropia*, *Neoporphyra*, *Phycocalidia* 및 *Asparagopsis*의 최신 학술 논문을 
          엄선하여 핵심 요약, 시사점, 에디터 트렌드 브리핑과 함께 제공합니다.
        </p>

        <!-- 핵심 통계 배지 -->
        <div class="mt-6 flex flex-wrap gap-4 pt-2">
          <div class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            <span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
            이번 호 분석 논문: <strong id="stat-papers" class="text-slate-900 dark:text-white">24편</strong>
          </div>
          <div class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            <span class="w-2.5 h-2.5 rounded-full bg-ocean-500"></span>
            포함 생물군: <strong id="stat-taxa" class="text-slate-900 dark:text-white">6개 속</strong>
          </div>
          <div class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            <span class="w-2.5 h-2.5 rounded-full bg-cyan-500"></span>
            발행 주기: <strong class="text-slate-900 dark:text-white">매주 수요일 정기 발행</strong>
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
            class="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-deepsea-900 text-sm focus:outline-none focus:ring-2 focus:ring-ocean-500 dark:focus:ring-ocean-400 transition" />
        </div>
        <div class="flex items-center gap-3 w-full sm:w-auto justify-end">
          <span class="text-xs text-slate-500 dark:text-slate-400">검색 매칭: <strong id="filter-count" class="text-ocean-600 dark:text-ocean-400 font-bold">24</strong>건</span>
          <button id="reset-filters" class="text-xs px-2.5 py-1.5 text-slate-500 hover:text-slate-800 dark:hover:text-white transition underline">
            필터 초기화
          </button>
        </div>
      </div>

      <!-- 생물군 버튼 필터 -->
      <div class="flex items-center gap-1.5 flex-wrap pt-2 border-t border-slate-100 dark:border-slate-800/60 text-xs">
        <span class="text-slate-400 text-[11px] font-semibold mr-1 flex items-center gap-1">
          <i data-lucide="tag" class="w-3 h-3"></i> 생물군 필터:
        </span>
        <button data-taxa="all" class="taxa-btn px-2.5 py-1 rounded-md text-[11px] font-bold bg-slate-300 dark:bg-slate-700 text-slate-900 dark:text-slate-100">전체보기</button>
        <button data-taxa="Pyropia" class="taxa-btn px-2.5 py-1 rounded-md text-[11px] font-medium bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 border border-slate-200 dark:border-slate-700">Pyropia (김속)</button>
        <button data-taxa="Porphyra" class="taxa-btn px-2.5 py-1 rounded-md text-[11px] font-medium bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 border border-slate-200 dark:border-slate-700">Porphyra (원형 김)</button>
        <button data-taxa="Neopyropia" class="taxa-btn px-2.5 py-1 rounded-md text-[11px] font-medium bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 border border-slate-200 dark:border-slate-700">Neopyropia (방사무늬김)</button>
        <button data-taxa="Neoporphyra" class="taxa-btn px-2.5 py-1 rounded-md text-[11px] font-medium bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 border border-slate-200 dark:border-slate-700">Neoporphyra (모무늬돌김)</button>
        <button data-taxa="Phycocalidia" class="taxa-btn px-2.5 py-1 rounded-md text-[11px] font-medium bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 border border-slate-200 dark:border-slate-700">Phycocalidia (둥근돌김류)</button>
        <button data-taxa="Asparagopsis" class="taxa-btn px-2.5 py-1 rounded-md text-[11px] font-medium bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 border border-slate-200 dark:border-slate-700">Asparagopsis (바다고리풀)</button>
      </div>
    </div>
  </section>

  <!-- 매거진 본문: 3대 카테고리별 섹션 구역 분리 -->
  <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-16">

    <!-- ========================================== -->
    <!-- SECTION 01: 육종 · 분자생물학 · 병해 -->
    <!-- ========================================== -->
    <section id="sec-breeding" class="scroll-mt-32">
      <!-- 섹션 헤더 -->
      <div class="flex flex-col sm:flex-row sm:items-end justify-between border-b-2 border-rose-500 pb-3 mb-6">
        <div>
          <span class="text-xs font-black tracking-widest text-rose-600 dark:text-rose-400 uppercase">SECTION 01</span>
          <h2 class="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white flex items-center gap-2">
            <span>🧬 육종 · 분자생물학 · 병해</span>
            <span class="text-sm font-normal text-slate-400">(Breeding & Pathology)</span>
          </h2>
        </div>
        <span id="badge-count-breeding" class="text-xs font-semibold px-2.5 py-1 rounded-full bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300 w-fit mt-2 sm:mt-0">
          0편 수록
        </span>
      </div>

      <!-- Editor's Weekly Insight -->
      <div class="rounded-2xl bg-gradient-to-r from-rose-500/10 via-rose-500/5 to-transparent border border-rose-200 dark:border-rose-900/60 p-5 mb-8 shadow-sm">
        <div class="flex items-center gap-2 text-rose-800 dark:text-rose-300 font-bold text-sm mb-2">
          <i data-lucide="feather" class="w-4 h-4 text-rose-600"></i>
          <span>Editor's Weekly Insight: <span id="insight-title-breeding" class="font-extrabold">기후 온난화 대응 내열성 분자마커와 병해 전사체 고도화</span></span>
        </div>
        <p id="insight-content-breeding" class="text-xs sm:text-sm text-slate-700 dark:text-slate-300 leading-relaxed font-normal">
          이번 주 육종 및 병해 연구 트렌드는 해수 온도 상승에 따른 내삼투압/열충격 단백질(HSP) 발현 메커니즘 규명과 더불어, 주요 병원체(Pythium porphyrae)에 대응하는 방어 전사인자(bZIP, MYB) 동정이 두드러집니다. 다중 오믹스 분석을 통한 유용 유전자원 선발이 양식장 현장 품종 개량의 핵심 열쇠로 자리잡고 있습니다.
        </p>
      </div>

      <!-- 카드 그리드 -->
      <div id="grid-breeding" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <!-- JS 주입 -->
      </div>
    </section>


    <!-- ========================================== -->
    <!-- SECTION 02: 엽체 · 생활사 · 양식·배양 -->
    <!-- ========================================== -->
    <section id="sec-cultivation" class="scroll-mt-32">
      <!-- 섹션 헤더 -->
      <div class="flex flex-col sm:flex-row sm:items-end justify-between border-b-2 border-emerald-500 pb-3 mb-6">
        <div>
          <span class="text-xs font-black tracking-widest text-emerald-600 dark:text-emerald-400 uppercase">SECTION 02</span>
          <h2 class="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white flex items-center gap-2">
            <span>🌱 엽체 생리 · 생활사 · 스마트 양식</span>
            <span class="text-sm font-normal text-slate-400">(Thallus & Cultivation)</span>
          </h2>
        </div>
        <span id="badge-count-cultivation" class="text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 w-fit mt-2 sm:mt-0">
          0편 수록
        </span>
      </div>

      <!-- Editor's Weekly Insight -->
      <div class="rounded-2xl bg-gradient-to-r from-emerald-500/10 via-emerald-500/5 to-transparent border border-emerald-200 dark:border-emerald-900/60 p-5 mb-8 shadow-sm">
        <div class="flex items-center gap-2 text-emerald-800 dark:text-emerald-300 font-bold text-sm mb-2">
          <i data-lucide="feather" class="w-4 h-4 text-emerald-600"></i>
          <span>Editor's Weekly Insight: <span id="insight-title-cultivation" class="font-extrabold">패각 대체 스마트 사상체 배양과 영양염 대사 적응 전략</span></span>
        </div>
        <p id="insight-content-cultivation" class="text-xs sm:text-sm text-slate-700 dark:text-slate-300 leading-relaxed font-normal">
          엽체 생리 및 양식 기술 분야에서는 기존 굴패각 배양의 한계를 뛰어넘는 액체 통기 자유사상체 배양 조건과 연안 영양염(N, P) 결핍에 대응하는 periplasmic alkaline phosphatase 등의 효소 기전이 집중 조명되었습니다. 스마트 육상 채묘 및 환경 제어형 시스템의 경제성 확보가 핵심 과제로 부각되고 있습니다.
        </p>
      </div>

      <!-- 카드 그리드 -->
      <div id="grid-cultivation" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <!-- JS 주입 -->
      </div>
    </section>


    <!-- ========================================== -->
    <!-- SECTION 03: 블루카본 · 저메탄 사료 · 기후대응 -->
    <!-- ========================================== -->
    <section id="sec-bluecarbon" class="scroll-mt-32">
      <!-- 섹션 헤더 -->
      <div class="flex flex-col sm:flex-row sm:items-end justify-between border-b-2 border-cyan-500 pb-3 mb-6">
        <div>
          <span class="text-xs font-black tracking-widest text-cyan-600 dark:text-cyan-400 uppercase">SECTION 03</span>
          <h2 class="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white flex items-center gap-2">
            <span>🌍 블루카본 · 저메탄 사료 · 기후대응</span>
            <span class="text-sm font-normal text-slate-400">(Blue Carbon & Climate Solutions)</span>
          </h2>
        </div>
        <span id="badge-count-bluecarbon" class="text-xs font-semibold px-2.5 py-1 rounded-full bg-cyan-100 text-cyan-800 dark:bg-cyan-950 dark:text-cyan-300 w-fit mt-2 sm:mt-0">
          0편 수록
        </span>
      </div>

      <!-- Editor's Weekly Insight -->
      <div class="rounded-2xl bg-gradient-to-r from-cyan-500/10 via-cyan-500/5 to-transparent border border-cyan-200 dark:border-cyan-900/60 p-5 mb-8 shadow-sm">
        <div class="flex items-center gap-2 text-cyan-800 dark:text-cyan-300 font-bold text-sm mb-2">
          <i data-lucide="feather" class="w-4 h-4 text-cyan-600"></i>
          <span>Editor's Weekly Insight: <span id="insight-title-bluecarbon" class="font-extrabold">바다고리풀 메탄 감축 실증과 해양 탄소격리 플럭스 표준화</span></span>
        </div>
        <p id="insight-content-bluecarbon" class="text-xs sm:text-sm text-slate-700 dark:text-slate-300 leading-relaxed font-normal">
          블루카본 및 사료 분야는 Asparagopsis taxiformis의 장기 급여를 통한 반추위 장내 메탄 70~80% 억제 효과와 조직 내 브로모포름 잔류 안전성 검증이 핵심 성과로 보고되었습니다. 아울러 대형 홍조류의 연간 침적 유기탄소(POC/DOC)를 탄소배출권(mCDR)으로 공인받기 위한 정량적 방법론 연구가 급물살을 타고 있습니다.
        </p>
      </div>

      <!-- 카드 그리드 -->
      <div id="grid-bluecarbon" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <!-- JS 주입 -->
      </div>
    </section>

    <!-- 검색 결과 없을 때 -->
    <div id="empty-state" class="hidden text-center py-20 bg-white dark:bg-deepsea-900 rounded-2xl border border-slate-200 dark:border-slate-800">
      <i data-lucide="file-search" class="w-14 h-14 mx-auto text-slate-300 dark:text-slate-600 mb-3"></i>
      <h3 class="text-lg font-bold text-slate-800 dark:text-slate-200">일치하는 연구 논문이 없습니다</h3>
      <p class="text-xs text-slate-500 mt-1">다른 검색어나 생물군 태그(전체보기)를 선택해 보세요.</p>
    </div>

  </main>

  <!-- 플로팅 맨 위로 이동 버튼 -->
  <a href="#" class="fixed bottom-6 right-6 z-40 p-3 rounded-full bg-ocean-600 text-white shadow-lg hover:bg-ocean-700 transition flex items-center justify-center" title="맨 위로 가기">
    <i data-lucide="arrow-up" class="w-5 h-5"></i>
  </a>

  <!-- 지난 아카이브 모달 -->
  <div id="archive-modal" class="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm hidden flex items-center justify-center p-4">
    <div class="glass-panel w-full max-w-xl rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-2xl space-y-4 max-h-[85vh] flex flex-col">
      <div class="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
        <div class="flex items-center gap-2">
          <i data-lucide="archive" class="w-5 h-5 text-ocean-600"></i>
          <h2 class="text-lg font-bold text-slate-900 dark:text-white">주차별 아카이브 호수 목록</h2>
        </div>
        <button id="close-modal" class="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
          <i data-lucide="x" class="w-5 h-5"></i>
        </button>
      </div>

      <p class="text-xs text-slate-500">매주 수요일마다 자동 아카이빙된 주간 연구 다이제스트입니다. 원하는 날짜를 선택하시면 해당 호수의 논문 브리핑으로 즉시 전환됩니다.</p>

      <div id="archive-list" class="space-y-2 overflow-y-auto pr-1 flex-1">
        <!-- JS 동적 생성 -->
      </div>

      <div class="pt-3 border-t border-slate-200 dark:border-slate-800 text-xs text-slate-400 flex items-center justify-between">
        <span>저장소 위치: <code class="text-ocean-600 dark:text-ocean-400">/archives/*.md</code></span>
        <span class="text-[11px]">GFM Markdown 호환</span>
      </div>
    </div>
  </div>

  <!-- 푸터 -->
  <footer class="mt-20 border-t border-slate-200 dark:border-slate-800 py-12 bg-white/70 dark:bg-deepsea-900/70">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-6 text-xs text-slate-500 dark:text-slate-400">
      <div>
        <p class="font-bold text-sm text-slate-800 dark:text-slate-200">PHYCO & BLUE CARBON RESEARCH MAGAZINE</p>
        <p class="mt-1">Automated Research Pipeline powered by GitHub Actions & Vercel Global Edge</p>
        <p class="mt-0.5 text-slate-400 text-[11px]">Target Genera: Pyropia, Porphyra, Neopyropia, Neoporphyra, Phycocalidia, Asparagopsis</p>
      </div>
      <div class="flex items-center space-x-4">
        <a href="https://github.com" target="_blank" class="hover:text-ocean-600 dark:hover:text-ocean-400 transition flex items-center gap-1 font-medium">
          <i data-lucide="github" class="w-4 h-4"></i> GitHub Repository
        </a>
        <span>•</span>
        <span>Every Wednesday Auto-Update</span>
      </div>
    </div>
  </footer>

  <!-- 클라이언트 로직 및 데이터 주입 -->
  <script>
    const INITIAL_ARCHIVE = {latest_json_str};
    const ALL_ARCHIVES = {index_json_str};

    let currentArchive = INITIAL_ARCHIVE;
    let selectedTaxa = 'all';
    let searchQuery = '';

    function initIcons() {{
      if (window.lucide) {{
        lucide.createIcons();
      }}
    }}

    // 다크모드 관리
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

    // 단일 논문 카드 렌더러 (요약 중심 + 토글형 초록 + 썸네일)
    function renderCard(art, idx) {{
      const taxaBadges = (art.taxa || []).map(t => 
        `<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-black/60 backdrop-blur-md text-white border border-white/20 italic">${{t}}</span>`
      ).join(' ');

      // 3가지 핵심 요약 포인트 렌더링
      const takeawaysList = (art.takeaways || []).map((point, pIdx) => `
        <li class="flex items-start gap-2 text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
          <span class="shrink-0 w-4 h-4 rounded-full bg-ocean-100 dark:bg-ocean-950 text-ocean-700 dark:text-ocean-300 flex items-center justify-center text-[10px] font-bold mt-0.5 border border-ocean-300 dark:border-ocean-800">
            ${{pIdx + 1}}
          </span>
          <span>${{point}}</span>
        </li>
      `).join('');

      const cleanAbstract = (art.abstract || '초록 정보가 제공되지 않는 논문입니다.').replaceAll('###', '').replaceAll('####', '').replaceAll('**', '').trim();

      return `
        <article class="flex flex-col justify-between rounded-2xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-deepsea-900 shadow-sm hover:shadow-xl hover:border-ocean-300 dark:hover:border-ocean-600 transition-all duration-300 overflow-hidden group">
          <div>
            <!-- 상단 16:9 썸네일 배너 -->
            <div class="relative h-48 w-full overflow-hidden bg-slate-100 dark:bg-slate-800">
              <img src="${{art.thumbnail_url}}" alt="${{art.headline}}" 
                class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500 ease-out" 
                loading="lazy" />
              <div class="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent"></div>
              
              <!-- 이미지 위 플로팅 배지 -->
              <div class="absolute top-3 left-3 flex flex-wrap gap-1">
                ${{taxaBadges}}
              </div>
              <div class="absolute top-3 right-3">
                <span class="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-white/90 dark:bg-black/80 backdrop-blur-md text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-700">
                  ${{art.journal || 'Journal'}}
                </span>
              </div>
              
              <!-- 이미지 하단 원문 서지정보 오버레이 -->
              <div class="absolute bottom-2.5 left-3 right-3 text-[11px] text-white/90 truncate">
                <i data-lucide="user" class="w-3 h-3 inline mr-1 text-ocean-300"></i> ${{art.authors || 'Authors'}}
              </div>
            </div>

            <!-- 카드 본문 콘텐츠 -->
            <div class="p-5 sm:p-6 space-y-4">
              
              <!-- ① 직관적인 한 줄 헤드라인 -->
              <h3 class="text-base sm:text-lg font-bold text-slate-900 dark:text-white group-hover:text-ocean-600 dark:group-hover:text-ocean-400 transition-colors leading-snug line-clamp-2">
                <a href="${{art.url}}" target="_blank" rel="noopener noreferrer">
                  ${{art.headline}}
                </a>
              </h3>

              <!-- 원문 논문 제목 (보조 타이틀) -->
              <p class="text-xs text-slate-500 dark:text-slate-400 line-clamp-2 font-mono">
                ${{art.title}}
              </p>

              <!-- ② 3가지 핵심 요약 포인트 (Key Takeaways) -->
              <div class="pt-3 border-t border-slate-100 dark:border-slate-800/80">
                <h4 class="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider mb-2.5 flex items-center gap-1.5">
                  <i data-lucide="check-circle-2" class="w-3.5 h-3.5 text-emerald-500"></i>
                  <span>Key Takeaways (핵심 성과)</span>
                </h4>
                <ul class="space-y-2">
                  ${{takeawaysList}}
                </ul>
              </div>

              <!-- ③ 연구자 시사점 (Researcher's Takeaway) -->
              ${{art.implications ? `
                <div class="p-3 rounded-xl bg-ocean-50/80 dark:bg-ocean-950/50 border border-ocean-200/80 dark:border-ocean-900/60">
                  <h5 class="text-[11px] font-bold text-ocean-800 dark:text-ocean-300 uppercase tracking-wider mb-1 flex items-center gap-1">
                    <i data-lucide="lightbulb" class="w-3 h-3 text-amber-500"></i>
                    <span>Researcher's Takeaway (시사점)</span>
                  </h5>
                  <p class="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
                    ${{art.implications}}
                  </p>
                </div>
              ` : ''}}

              <!-- [초록 보기 / 숨기기] 토글 버튼 및 접이식 본문 -->
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
                    <span>DOI: ${{art.doi || 'Linked'}}</span>
                  </div>
                  ${{cleanAbstract}}
                </div>
              </div>

            </div>
          </div>

          <!-- 하단 푸터 액션 바 -->
          <div class="px-5 sm:px-6 py-3 border-t border-slate-100 dark:border-slate-800/80 bg-slate-50/50 dark:bg-deepsea-900/50 flex items-center justify-between">
            <span class="text-[11px] text-slate-400">${{art.journal || 'Academic Article'}} (${{art.year || '2026'}})</span>
            <a href="${{art.url}}" target="_blank" rel="noopener noreferrer" 
              class="inline-flex items-center gap-1.5 text-xs font-bold text-ocean-600 dark:text-ocean-400 hover:text-ocean-800 dark:hover:text-ocean-300 transition">
              <span>원문 열람 (DOI)</span>
              <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
            </a>
          </div>
        </article>
      `;
    }}

    // 섹션별 렌더링 함수
    function renderSections() {{
      const allArticles = currentArchive.articles || [];
      const emptyState = document.getElementById('empty-state');
      const filterCount = document.getElementById('filter-count');

      // 필터 적용
      const filtered = allArticles.filter(art => {{
        // 생물군 필터
        if (selectedTaxa !== 'all') {{
          const hasTaxa = (art.taxa || []).some(t => t.toLowerCase().includes(selectedTaxa.toLowerCase()));
          const matchTitle = (art.title || '').toLowerCase().includes(selectedTaxa.toLowerCase());
          const matchHead = (art.headline || '').toLowerCase().includes(selectedTaxa.toLowerCase());
          if (!hasTaxa && !matchTitle && !matchHead) return false;
        }}
        // 검색어 필터
        if (searchQuery.trim() !== '') {{
          const q = searchQuery.toLowerCase();
          const matchHead = (art.headline || '').toLowerCase().includes(q);
          const matchTitle = (art.title || '').toLowerCase().includes(q);
          const matchAuth = (art.authors || '').toLowerCase().includes(q);
          const matchAbs = (art.abstract || '').toLowerCase().includes(q);
          const matchTake = (art.takeaways || []).some(t => t.toLowerCase().includes(q));
          if (!matchHead && !matchTitle && !matchAuth && !matchAbs && !matchTake) return false;
        }}
        return true;
      }});

      filterCount.innerText = filtered.length;

      // 섹션별 분리
      const groups = {{
        breeding_molecular_pathology: [],
        thallus_lifecycle_cultivation: [],
        blue_carbon_feed_methane: []
      }};

      filtered.forEach((art, idx) => {{
        const cat = art.category || 'thallus_lifecycle_cultivation';
        if (groups[cat]) {{
          groups[cat].push({{ art, globalIdx: idx }});
        }} else {{
          groups.thallus_lifecycle_cultivation.push({{ art, globalIdx: idx }});
        }}
      }});

      // 각 그리드에 주입
      const gridBreeding = document.getElementById('grid-breeding');
      const gridCultivation = document.getElementById('grid-cultivation');
      const gridBluecarbon = document.getElementById('grid-bluecarbon');

      gridBreeding.innerHTML = groups.breeding_molecular_pathology.map(item => renderCard(item.art, item.globalIdx)).join('');
      gridCultivation.innerHTML = groups.thallus_lifecycle_cultivation.map(item => renderCard(item.art, item.globalIdx)).join('');
      gridBluecarbon.innerHTML = groups.blue_carbon_feed_methane.map(item => renderCard(item.art, item.globalIdx)).join('');

      // 섹션별 수치 배지 갱신
      document.getElementById('badge-count-breeding').innerText = `${{groups.breeding_molecular_pathology.length}}편 수록`;
      document.getElementById('badge-count-cultivation').innerText = `${{groups.thallus_lifecycle_cultivation.length}}편 수록`;
      document.getElementById('badge-count-bluecarbon').innerText = `${{groups.blue_carbon_feed_methane.length}}편 수록`;

      // 에디터 인사이트 텍스트 갱신 (아카이브에 저장된 인사이트 데이터 적용)
      const insights = currentArchive.editor_insights || {{}};
      if (insights.breeding_molecular_pathology) {{
        document.getElementById('insight-title-breeding').innerText = insights.breeding_molecular_pathology.title || '';
        document.getElementById('insight-content-breeding').innerText = insights.breeding_molecular_pathology.content || '';
      }}
      if (insights.thallus_lifecycle_cultivation) {{
        document.getElementById('insight-title-cultivation').innerText = insights.thallus_lifecycle_cultivation.title || '';
        document.getElementById('insight-content-cultivation').innerText = insights.thallus_lifecycle_cultivation.content || '';
      }}
      if (insights.blue_carbon_feed_methane) {{
        document.getElementById('insight-title-bluecarbon').innerText = insights.blue_carbon_feed_methane.title || '';
        document.getElementById('insight-content-bluecarbon').innerText = insights.blue_carbon_feed_methane.content || '';
      }}

      // 검색 결과 비어있을 때
      if (filtered.length === 0) {{
        emptyState.classList.remove('hidden');
      }} else {{
        emptyState.classList.add('hidden');
      }}

      initIcons();
    }}

    // [초록 원문 보기 / 숨기기] 토글 함수
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

    // 검색창 입력 이벤트
    document.getElementById('search-input').addEventListener('input', (e) => {{
      searchQuery = e.target.value;
      renderSections();
    }});

    // 생물군 필터 클릭
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

    // 지난 호수 모달 관리
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
            <h4 class="text-sm font-bold text-slate-800 dark:text-slate-200">${{arch.title}}</h4>
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
    modal.addEventListener('click', (e) => {{
      if (e.target === modal) modal.classList.add('hidden');
    }});

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
    renderSections();
    initIcons();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    build_site()
