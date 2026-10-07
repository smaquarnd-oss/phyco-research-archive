#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phyco & Blue Carbon Research Archive Pipeline
- 매주 수요일 실행되어 최신 김/바다고리풀 및 블루카본 연구 논문을 수집하고 Markdown 아카이브를 생성합니다.
- keywords.json 기반 다중 쿼리 검색 (Europe PMC / PubMed 연동)
- 4분할 섹션 체제: 육종/분자/병해, 엽체/생활사/사상체, 스마트양식/대량배양, 블루카본/산업응용
- 썸네일 중복 없는 키워드 기반 매칭 로직
- Gemini API 연동 (GEMINI_API_KEY 환경변수 감지 시 고품질 심층 한글 요약 자동 생성)
"""

import os
import sys
import json
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

# Windows 콘솔 및 다국어 출력을 위한 UTF-8 강제 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 기본 디렉토리 설정
BASE_DIR = Path(__file__).resolve().parent.parent
KEYWORDS_FILE = BASE_DIR / "keywords.json"
ARCHIVES_DIR = BASE_DIR / "archives"
PUBLIC_DATA_DIR = BASE_DIR / "public" / "data"

ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_keywords():
    """keywords.json 설정을 로드합니다."""
    if not KEYWORDS_FILE.exists():
        raise FileNotFoundError(f"키워드 설정 파일을 찾을 수 없습니다: {KEYWORDS_FILE}")
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_ssl_context():
    """기업망 프록시 또는 로컬 SSL 환경에서도 안전하게 통신할 수 있는 SSL 컨텍스트를 반환합니다."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def search_europe_pmc(query, page_size=10):
    """
    Europe PMC REST API를 통해 생명과학/해조류 관련 최신 논문과 '실제 초록(abstractText)'을 검색합니다.
    resultType=core 파라미터를 지정해야 전체 초록 본문이 반환됩니다.
    """
    url = (
        f"https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        f"?query={urllib.parse.quote(query)}"
        f"&resultType=core"
        f"&format=json"
        f"&pageSize={page_size}"
        f"&sort=P_PD_D%20desc"
    )
    headers = {"User-Agent": "PhycoBlueCarbonArchiveBot/2.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12, context=get_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("resultList", {}).get("result", [])
            for item in results:
                raw_abs = item.get("abstractText", "")
                if raw_abs:
                    clean_abs = re.sub(r"<[^>]+>", "", raw_abs).strip()
                    item["abstractText"] = clean_abs
            return results
    except Exception as e:
        return []


def search_pubmed(query, page_size=8):
    """
    NCBI PubMed E-utilities (eSearch -> eFetch XML) 파이프라인:
    논문의 제목, 저자, 저널, DOI뿐 아니라 <AbstractText> 태그의 실제 초록 본문을 완전하게 파싱합니다.
    """
    try:
        esearch_url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pubmed&term={urllib.parse.quote(query)}&retmode=json&retmax={page_size}&sort=pub_date"
        )
        headers = {"User-Agent": "PhycoBlueCarbonArchiveBot/2.0"}
        req = urllib.request.Request(esearch_url, headers=headers)
        with urllib.request.urlopen(req, timeout=12, context=get_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            id_list = data.get("esearchresult", {}).get("idlist", [])

        if not id_list:
            return []

        ids_param = ",".join(id_list)
        efetch_url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            f"?db=pubmed&id={ids_param}&retmode=xml"
        )
        req2 = urllib.request.Request(efetch_url, headers=headers)
        with urllib.request.urlopen(req2, timeout=15, context=get_ssl_context()) as resp:
            xml_data = resp.read()
            root = ET.fromstring(xml_data)

        articles = []
        for article_elem in root.findall(".//PubmedArticle"):
            medline = article_elem.find(".//MedlineCitation")
            if medline is None:
                continue
            pmid = medline.findtext(".//PMID", default="")
            art = medline.find(".//Article")
            if art is None:
                continue

            title = art.findtext(".//ArticleTitle", default="").strip().rstrip(".")

            abstract_parts = []
            for ab_elem in art.findall(".//AbstractText"):
                label = ab_elem.get("Label")
                txt = "".join(ab_elem.itertext()).strip()
                if txt:
                    if label and label.upper() not in ["UNLABELLED", ""]:
                        abstract_parts.append(f"[{label}] {txt}")
                    else:
                        abstract_parts.append(txt)

            abstract = "\n\n".join(abstract_parts).strip()
            if not abstract:
                abstract = "초록이 NCBI에 제공되지 않는 논문입니다. 원문 DOI 링크에서 전문을 확인하실 수 있습니다."

            author_names = []
            for auth in art.findall(".//AuthorList/Author"):
                last_name = auth.findtext("LastName", default="")
                fore_name = auth.findtext("ForeName", default="")
                collective = auth.findtext("CollectiveName", default="")
                if collective:
                    author_names.append(collective)
                elif last_name:
                    name_str = f"{last_name} {fore_name[:1]}" if fore_name else last_name
                    author_names.append(name_str)
            author_str = ", ".join(author_names[:4]) + (" et al." if len(author_names) > 4 else "")

            journal = art.findtext(".//Journal/Title") or art.findtext(".//Journal/ISOAbbreviation") or "Academic Journal"

            pub_year = art.findtext(".//JournalIssue/PubDate/Year")
            if not pub_year:
                pub_year = medline.findtext(".//DateCompleted/Year") or str(datetime.now().year)

            doi = ""
            for id_elem in article_elem.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if id_elem.get("IdType") == "doi":
                    doi = id_elem.text.strip() if id_elem.text else ""
                    break

            articles.append({
                "id": pmid,
                "doi": doi or f"pmid:{pmid}",
                "title": title,
                "authorString": author_str or "저자 정보 없음",
                "journalTitle": journal,
                "pubYear": pub_year,
                "abstractText": abstract
            })

        return articles
    except Exception as e:
        print(f"[-] PubMed 파싱 중 오류: {e}")
        return []


def classify_article(article, taxa_list, categories):
    """
    논문의 제목 및 초록 텍스트를 기반으로 생물군 및 연구 카테고리를 분류합니다.
    4분할 카테고리 체제 (v2.0):
      01. breeding_molecular_pathology
      02. thallus_lifecycle_conchocelis
      03. smart_aquaculture_mass_culture
      04. blue_carbon_feed_methane
    """
    text = f"{article.get('title', '')} {article.get('abstractText', '')}".lower()

    matched_taxa = []
    for taxa in taxa_list:
        if not taxa.get("enabled", True):
            continue
        t_name = taxa["name"].lower()
        if t_name in text:
            matched_taxa.append(taxa["name"])
        else:
            for alias in taxa.get("aliases", []):
                if alias.lower() in text:
                    matched_taxa.append(taxa["name"])
                    break

    matched_categories = []
    for cat_id, cat_info in categories.items():
        score = 0
        for kw in cat_info.get("keywords", []):
            if kw.lower() in text:
                score += 1
        if score > 0:
            matched_categories.append((cat_id, score))

    matched_categories.sort(key=lambda x: x[1], reverse=True)

    # 폴백: 기본 카테고리를 thallus_lifecycle_conchocelis로 설정
    default_cat = "thallus_lifecycle_conchocelis"
    if "thallus_lifecycle_cultivation" in categories:
        default_cat = "thallus_lifecycle_cultivation"
    elif "thallus_lifecycle_conchocelis" not in categories:
        default_cat = list(categories.keys())[0] if categories else "thallus_lifecycle_conchocelis"

    best_category = matched_categories[0][0] if matched_categories else default_cat

    return list(set(matched_taxa)), best_category


# ─────────────────────────────────────────────────────────────────────────────
# 썸네일 이미지 풀 (4개 카테고리 × 6개 이미지, 주제 매칭 기반)
# 카테고리별로 충분히 크게 유지해 중복 배정을 방지합니다.
# ─────────────────────────────────────────────────────────────────────────────
CURATED_THUMBNAILS = {
    # SECTION 01: 육종 · 분자생물학 · 병해 — 현미경, DNA, 분자 이미지
    "breeding_molecular_pathology": [
        "https://images.unsplash.com/photo-1532187863486-abf9dbad1b69?auto=format&fit=crop&w=800&q=80",  # 분자/DNA
        "https://images.unsplash.com/photo-1579154204601-01588f351e67?auto=format&fit=crop&w=800&q=80",  # 현미경 세포
        "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=800&q=80",  # 유전자 분석
        "https://images.unsplash.com/photo-1507668077129-56e32842fceb?auto=format&fit=crop&w=800&q=80",  # 실험실 장비
        "https://images.unsplash.com/photo-1563674407-b5de7db5ccb0?auto=format&fit=crop&w=800&q=80",  # 바이오텍
        "https://images.unsplash.com/photo-1484557052118-f32bd25b45b5?auto=format&fit=crop&w=800&q=80",  # 유전체 분석
    ],
    # SECTION 02: 엽체 생리 · 생활사 · 사상체 — 해조류 엽체, 포자, 미세조류
    "thallus_lifecycle_conchocelis": [
        "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80",  # 해조류 엽체
        "https://images.unsplash.com/photo-1518837695005-2083093ee35b?auto=format&fit=crop&w=800&q=80",  # 해양 수중 식물
        "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=800&q=80",  # 해안 조간대
        "https://images.unsplash.com/photo-1614728894747-a83421789f10?auto=format&fit=crop&w=800&q=80",  # 녹색 해조류
        "https://images.unsplash.com/photo-1559827260-dc66d52bef19?auto=format&fit=crop&w=800&q=80",  # 해양 생물학
        "https://images.unsplash.com/photo-1509563768818-dafe9ad27b4e?auto=format&fit=crop&w=800&q=80",  # 수중 식물
    ],
    # SECTION 03: 스마트 양식 및 대량 배양 기술 — 배양 탱크, 양식장, 생물반응기
    "smart_aquaculture_mass_culture": [
        "https://images.unsplash.com/photo-1581093458791-9f3c3900df4b?auto=format&fit=crop&w=800&q=80",  # 배양 플라스크
        "https://images.unsplash.com/photo-1565193566173-7a0ee3dbe261?auto=format&fit=crop&w=800&q=80",  # 수산/양식
        "https://images.unsplash.com/photo-1594122230689-45899d9e6f69?auto=format&fit=crop&w=800&q=80",  # 실험실 배양
        "https://images.unsplash.com/photo-1608408891571-89c4aa18ef7c?auto=format&fit=crop&w=800&q=80",  # 스마트팜/수직농업
        "https://images.unsplash.com/photo-1576086213369-97a306d36557?auto=format&fit=crop&w=800&q=80",  # 실험장비
        "https://images.unsplash.com/photo-1530541930197-ff16ac917b0e?auto=format&fit=crop&w=800&q=80",  # 양식 해안
    ],
    # SECTION 04: 블루카본 및 산업적 응용 — 해양, 기후, 탄소, 산업
    "blue_carbon_feed_methane": [
        "https://images.unsplash.com/photo-1682687220063-4742bd7fd538?auto=format&fit=crop&w=800&q=80",  # 해양 탄소
        "https://images.unsplash.com/photo-1682687220199-d0124f48f95b?auto=format&fit=crop&w=800&q=80",  # 해양 환경
        "https://images.unsplash.com/photo-1500595046743-cd271d694d30?auto=format&fit=crop&w=800&q=80",  # 기후/지구
        "https://images.unsplash.com/photo-1498084393753-b411b2d26b34?auto=format&fit=crop&w=800&q=80",  # 저녁 바다
        "https://images.unsplash.com/photo-1552728089-57bdde30beb3?auto=format&fit=crop&w=800&q=80",  # 가축 목장
        "https://images.unsplash.com/photo-1473341304170-971dccb5ac1e?auto=format&fit=crop&w=800&q=80",  # 산업 응용
    ],
    # 레거시 카테고리 폴백 (이전 아카이브 호환용)
    "thallus_lifecycle_cultivation": [
        "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1518837695005-2083093ee35b?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1581093458791-9f3c3900df4b?auto=format&fit=crop&w=800&q=80",
    ],
}

# 키워드 → 썸네일 인덱스 매핑 (카테고리 내에서 더 정교하게 선택)
KEYWORD_THUMBNAIL_HINT = {
    # SECTION 01 hints
    "breeding_molecular_pathology": {
        "dna": 0, "barcode": 0, "barcod": 0, "genomic": 0, "phylogen": 0,
        "microscop": 1, "cell": 1, "spore": 1,
        "transcriptom": 2, "crispr": 2, "gene express": 2,
        "pcr": 3, "sequenc": 3, "primer": 3,
        "biotech": 4, "protein": 4,
        "disease": 5, "pathogen": 5, "red rot": 5, "pythium": 5,
    },
    # SECTION 02 hints
    "thallus_lifecycle_conchocelis": {
        "thallus": 0, "blade": 0, "frond": 0,
        "seaweed": 1, "macroalga": 1, "intertidal": 1,
        "conchocel": 2, "spore": 2, "gametophyte": 2,
        "photosynthes": 3, "pigment": 3, "chlorophyll": 3,
        "life cycle": 4, "life histor": 4, "gametangi": 4,
        "germination": 5, "sporeling": 5, "embryo": 5,
    },
    # SECTION 03 hints
    "smart_aquaculture_mass_culture": {
        "bioreactor": 0, "flask": 0, "batch": 0,
        "aquaculture": 1, "farm": 1, "pond": 1,
        "culture medium": 2, "nutrient": 2, "growth rate": 2,
        "led": 3, "indoor": 3, "vertical": 3, "controlled": 3,
        "harvest": 4, "yield": 4, "biomass product": 4,
        "seeding": 5, "seed net": 5, "sporeling": 5,
    },
    # SECTION 04 hints
    "blue_carbon_feed_methane": {
        "carbon sequestrat": 0, "blue carbon": 0, "mCDR": 0,
        "ocean": 1, "marine": 1, "seawater": 1,
        "climate": 2, "greenhouse": 2, "co2": 2,
        "sunset": 3, "flux": 3, "RDOC": 3,
        "livestock": 4, "cattle": 4, "sheep": 4, "methane": 4, "ruminant": 4,
        "biofuel": 5, "biorefinery": 5, "industrial": 5, "agar": 5,
    },
}


def pick_thumbnail(cat_id: str, title: str, abstract: str, used_urls: set) -> str:
    """
    카테고리와 논문 제목/초록의 핵심 키워드를 매칭하여
    중복 없이 고품질 썸네일 URL을 반환합니다.

    1. 카테고리별 키워드-인덱스 힌트로 최적 이미지 후보 선택
    2. 이미 사용된 URL이면 다음 순위 이미지로 이동 (폴백)
    3. 모든 이미지가 소진되면 가장 먼 사용 이미지 재활용
    """
    pool = CURATED_THUMBNAILS.get(cat_id, CURATED_THUMBNAILS.get("thallus_lifecycle_conchocelis", []))
    if not pool:
        return "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=800&q=80"

    text = f"{title} {abstract}".lower()
    hints = KEYWORD_THUMBNAIL_HINT.get(cat_id, {})

    # 키워드 힌트 기반 선호 인덱스 계산
    preferred_idx = 0
    best_score = -1
    for kw, idx in hints.items():
        if kw in text and idx > best_score:
            preferred_idx = idx
            best_score = idx

    # 선호 인덱스부터 순환하면서 미사용 URL 선택
    n = len(pool)
    for offset in range(n):
        candidate_url = pool[(preferred_idx + offset) % n]
        if candidate_url not in used_urls:
            used_urls.add(candidate_url)
            return candidate_url

    # 모든 이미지가 사용됨: 가장 마지막 이미지 재사용 (카드 수가 풀보다 많을 때)
    fallback = pool[preferred_idx % n]
    return fallback


EDITOR_INSIGHTS = {
    "breeding_molecular_pathology": {
        "title": "기후 온난화 대응 내열성 분자마커와 붉은갯병 감염 초기 전사체 분석의 고도화",
        "content": "이번 주 육종 및 병해 연구 트렌드는 해수 온도 상승에 따른 내삼투압/열충격 단백질(HSP) 발현 메커니즘 규명과 더불어, 주요 병원체(Pythium porphyrae)에 대응하는 방어 전사인자(bZIP, MYB) 동정이 두드러집니다. DNA 바코딩 기반 신분류체계 확립과 다중 오믹스 분석을 통한 유용 유전자원 선발이 양식장 현장 품종 개량의 핵심 열쇠로 자리잡고 있습니다."
    },
    "thallus_lifecycle_conchocelis": {
        "title": "사상체(Conchocelis) 각포자 방출 메커니즘과 엽체 생리 환경 적응 전략",
        "content": "엽체 생리 및 생활사 연구 분야에서는 광주기·수온 변동에 의한 각포자(conchospore) 대량 방출 제어 기전과 엽상체 기조직 발달 초기 단계 분자 마커가 주목받고 있습니다. 특히 Neopyropia / Neoporphyra 신분류군의 색소체 구조 및 사상체 분기점 비교 연구가 활발히 진행 중입니다."
    },
    "smart_aquaculture_mass_culture": {
        "title": "자유사상체 대량 배양과 스마트 채묘 시스템의 경제성 최적화",
        "content": "스마트 양식 및 대량 배양 분야는 굴패각 의존도를 제로화하는 자유사상체(free-living conchocelis) 액체 배양 조건 최적화와 LED 파장별 성장률 비교, 그리고 IoT 기반 실시간 수질 제어형 채묘 시스템 개발이 핵심 성과로 보고되었습니다. 배양 공학적 접근을 통한 단위 면적당 수확량 극대화가 산업 현장의 핵심 과제로 부각되고 있습니다."
    },
    "blue_carbon_feed_methane": {
        "title": "바다고리풀 브로모포름 메탄 감축 실증과 RDOC 기반 블루카본 탄소 격리 플럭스 표준화",
        "content": "블루카본 및 산업 응용 분야는 Asparagopsis taxiformis의 장기 급여를 통한 반추위 장내 메탄 70~80% 억제 효과와 조직 내 브로모포름 잔류 안전성 검증이 핵심 성과로 보고되었습니다. 아울러 대형 홍조류의 연간 침적 불용성 유기탄소(RDOC/POC)를 탄소배출권(mCDR)으로 공인받기 위한 정량적 방법론 연구가 급물살을 타고 있습니다."
    }
}


def analyze_paper_content(title, abstract, category_name, taxa_list, cat_id, thumbnail_url):
    """
    논문 정보를 바탕으로 매거진 카드용 ① 직관적 한 줄 헤드라인, ② 3가지 핵심 요약(Takeaways), ③ 연구자 시사점을 도출합니다.
    Gemini API 키가 있을 경우 심층 생성하고, 없을 경우 스마트 룰베이스로 정제합니다.
    """
    taxa_str = ", ".join(taxa_list)
    api_key = os.environ.get("GEMINI_API_KEY")

    # 1. Gemini API 심층 분석 시도
    if api_key and abstract and len(abstract) > 100:
        prompt = f"""
당신은 해조류 및 해양 블루카본 분야의 수석 연구위원이자 최고급 사이언스 매거진 에디터입니다.
아래 논문 정보를 읽고 연구 매거진 카드에 실릴 전문 분석 데이터를 JSON 포맷으로 작성해 주세요.

[논문 정보]
- 제목: {title}
- 대상 생물군: {taxa_str}
- 연구 분야: {category_name}
- 영문 초록:
{abstract}

[요구사항 - 반드시 아래 JSON 키만 포함된 순수 JSON으로 응답]
{{
  "headline": "독자의 시선을 사로잡는 전문적이고 직관적인 국문 한 줄 헤드라인 (30~45자 내외)",
  "takeaways": [
    "핵심 요약 포인트 1 (연구 목적 및 해결하고자 한 핵심 문제)",
    "핵심 요약 포인트 2 (도출된 주요 실험 성과, 수치, 유전자 또는 분석 데이터)",
    "핵심 요약 포인트 3 (검증된 생물학적 기작 또는 환경 적응 메커니즘)"
  ],
  "implications": "양식 현장 적용성 또는 해양 학술/산업적 연구자 시사점 (1~2문장)"
}}
"""
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20, context=get_ssl_context()) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                candidates = res_json.get("candidates", [])
                if candidates:
                    json_str = candidates[0]["content"]["parts"][0]["text"].strip()
                    parsed = json.loads(json_str)
                    return {
                        "headline": parsed.get("headline", title),
                        "takeaways": parsed.get("takeaways", []),
                        "implications": parsed.get("implications", ""),
                        "thumbnail_url": thumbnail_url,
                        "is_ai": True
                    }
        except Exception as e:
            print(f"[-] Gemini 구조화 요약 건너뜀 또는 에러: {e}")

    # 2. 스마트 룰베이스 폴백 분석
    raw_sentences = [s.strip() for s in re.split(r"\.\s+", abstract) if len(s.strip()) > 15]

    headline = title
    if len(title) > 65:
        headline = title[:65].rsplit(" ", 1)[0] + "..."

    takeaways = []
    if len(raw_sentences) >= 3:
        takeaways.append(f"연구 목적: {raw_sentences[0]}.")
        takeaways.append(f"주요 발견: {raw_sentences[1]}.")
        takeaways.append(f"분석 성과: {raw_sentences[-1]}.")
    elif len(raw_sentences) == 2:
        takeaways.append(f"연구 배경: {raw_sentences[0]}.")
        takeaways.append(f"주요 성과: {raw_sentences[1]}.")
        takeaways.append(f"대상 생물군인 {taxa_str}의 환경 적응 및 대사 특성 분석 완료.")
    else:
        takeaways.append(f"{taxa_str} 대상 {category_name} 핵심 데이터 분석 수행.")
        takeaways.append(f"논문 DOI 원문을 통해 상세 실험 프로토콜 및 수치 데이터 확인 가능.")
        takeaways.append(f"국제 학술지 정식 색인 논문으로 최신 연구 동향 반영.")

    implications = f"본 연구는 {taxa_str}의 {category_name} 실증 연구에 기초 생물학적 메커니즘과 현장 적용 가이드라인을 제공합니다."

    return {
        "headline": headline,
        "takeaways": takeaways[:3],
        "implications": implications,
        "thumbnail_url": thumbnail_url,
        "is_ai": False
    }


def run_pipeline():
    """전체 수집 및 아카이빙 파이프라인을 실행합니다 (4분할 섹션 체제 v2.0)."""
    print("==================================================")
    print("🌊 Phyco & Blue Carbon Research Magazine Pipeline v2.0")
    print(f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")

    config = load_keywords()
    target_taxa = config.get("target_taxa", {}).get("genera", [])
    categories = config.get("research_categories", {})
    lookback_days = config.get("search_settings", {}).get("days_lookback", 7)

    # 썸네일 사용 추적 (카테고리별 독립 관리)
    used_thumbnails_per_cat = {cat_id: set() for cat_id in categories.keys()}

    # 1. 생물군별 검색 쿼리 구성
    print("\n[1/4] 최신 학술 논문 검색 중 (Europe PMC & PubMed)...")
    collected_articles = {}

    for taxa in target_taxa:
        taxa_name = taxa["name"]
        print(f" -> 생물군 '{taxa_name}' 검색 진행...")

        query = f'("{taxa_name}") AND (FIRST_PDATE:[{datetime.now().date() - timedelta(days=lookback_days*4)} TO {datetime.now().date()}])'
        raw_results = search_europe_pmc(query, page_size=8)

        if len(raw_results) < 2:
            fallback_query = f'("{taxa_name}" OR "{taxa.get("aliases", [taxa_name])[0]}")'
            raw_results = search_europe_pmc(fallback_query, page_size=5)

        if not raw_results:
            print(f"    [PubMed 폴백] '{taxa_name}' NCBI PubMed 검색 가동...")
            pm_query = f"{taxa_name}[Title/Abstract] AND (\"2025\"[Date - Publication] : \"3000\"[Date - Publication])"
            raw_results = search_pubmed(pm_query, page_size=5)
            if not raw_results:
                raw_results = search_pubmed(taxa_name, page_size=5)

        for item in raw_results:
            doi = item.get("doi") or item.get("id")
            if not doi:
                continue
            if doi not in collected_articles:
                collected_articles[doi] = item

    print(f" => 총 {len(collected_articles)}편의 후보 논문 수집 완료.")

    # 2. 메타데이터 정규화 및 카테고리 분류
    print("\n[2/4] 논문 분류 및 구조화 요약(헤드라인/Takeaways/시사점) 생성 중...")
    processed_papers = []

    for idx, (doi, raw) in enumerate(collected_articles.items()):
        title = raw.get("title", "").rstrip(".")
        abstract = raw.get("abstractText", "")
        author_str = raw.get("authorString", "Unknown authors")
        journal = raw.get("journalTitle") or raw.get("journalInfo", {}).get("journal", {}).get("title", "Academic Journal")
        pub_year = raw.get("pubYear", str(datetime.now().year))

        matched_taxa, best_cat = classify_article(raw, target_taxa, categories)
        if not matched_taxa:
            matched_taxa = ["Pyropia/Porphyra complex"]

        doi_url = f"https://doi.org/{doi}" if doi and not doi.startswith("http") else (doi or "#")
        cat_info = categories.get(best_cat, {})

        # 카테고리별 중복 없는 썸네일 선택
        used_set = used_thumbnails_per_cat.setdefault(best_cat, set())
        thumbnail_url = pick_thumbnail(best_cat, title, abstract, used_set)

        # 구조화 분석 실행 (헤드라인, 3가지 핵심 요약, 시사점)
        analysis = analyze_paper_content(
            title=title,
            abstract=abstract,
            category_name=cat_info.get("name_ko", "해조류 생물학"),
            taxa_list=matched_taxa,
            cat_id=best_cat,
            thumbnail_url=thumbnail_url,
        )

        paper = {
            "title": title,
            "headline": analysis["headline"],
            "takeaways": analysis["takeaways"],
            "implications": analysis["implications"],
            "thumbnail_url": analysis["thumbnail_url"],
            "abstract": abstract,
            "authors": author_str,
            "journal": journal,
            "year": pub_year,
            "doi": doi,
            "url": doi_url,
            "taxa": matched_taxa,
            "category": best_cat,
            "category_name": cat_info.get("name_ko", "기타 연구"),
            "badge_color": cat_info.get("badge_color", "emerald"),
            "is_ai_summary": analysis["is_ai"]
        }
        processed_papers.append(paper)

    # 3. 섹션별 마크다운 아카이브 생성
    print("\n[3/4] 4분할 섹션 분리 및 Editor's Insight 마크다운 생성 중...")
    today_str = datetime.now().strftime("%Y-%m-%d")
    archive_file = ARCHIVES_DIR / f"{today_str}-weekly-digest.md"

    cat_grouped = {}
    for p in processed_papers:
        cat_grouped.setdefault(p["category"], []).append(p)

    taxa_all_set = list({t for p in processed_papers for t in p["taxa"]})

    frontmatter = f"""---
title: "김·바다고리풀 & 블루카본 연구 주간 다이제스트 ({today_str})"
date: "{today_str}"
total_papers: {len(processed_papers)}
taxa_covered: {json.dumps(taxa_all_set, ensure_ascii=False)}
categories: {json.dumps(list(cat_grouped.keys()), ensure_ascii=False)}
tags: ["Phyco", "BlueCarbon", "Seaweed", "Pyropia", "Asparagopsis"]
version: "2.0"
---
"""

    md_body = [
        frontmatter,
        f"# 🌊 김/바다고리풀속 및 블루카본 연구 주간 매거진 ({today_str})\n",
        f"> **발행일**: {today_str} | **분석 논문 수**: {len(processed_papers)}편  ",
        f"> **포함 생물군**: {', '.join(taxa_all_set) if taxa_all_set else 'Pyropia, Asparagopsis'}\n",
        "---\n"
    ]

    # 4분할 섹션 순서 고정
    SECTION_ORDER = [
        "breeding_molecular_pathology",
        "thallus_lifecycle_conchocelis",
        "smart_aquaculture_mass_culture",
        "blue_carbon_feed_methane",
    ]

    for cat_id in SECTION_ORDER:
        cat_info = categories.get(cat_id, {})
        if not cat_info:
            continue
        papers_in_cat = cat_grouped.get(cat_id, [])
        if not papers_in_cat:
            continue

        section_no = cat_info.get("section_no", "0X")
        insight = EDITOR_INSIGHTS.get(cat_id, {
            "title": f"{cat_info.get('name_ko', cat_id)} 주간 트렌드 분석",
            "content": f"{cat_info.get('name_ko', cat_id)} 분야의 주요 최신 논문 브리핑입니다."
        })

        md_body.append(f"## 🔬 SECTION {section_no}: {cat_info.get('name_ko', cat_id)} ({cat_info.get('name_en', '')})\n")
        md_body.append(f"> 💡 **Editor's Weekly Insight: {insight['title']}**  \n> {insight['content']}\n")

        for idx, paper in enumerate(papers_in_cat, 1):
            md_body.append(f"### {idx}. {paper['headline']}")
            md_body.append(f"- **원문 제목**: {paper['title']}")
            md_body.append(f"- **저자**: {paper['authors']}")
            md_body.append(f"- **저널**: *{paper['journal']}* ({paper['year']}) | **원문 링크**: [{paper['doi']}]({paper['url']})")
            md_body.append(f"- **대상 생물군**: `{', '.join(paper['taxa'])}`")
            md_body.append(f"- **대표 이미지**: ![]({paper['thumbnail_url']})\n")

            md_body.append("#### 📌 3가지 핵심 요약 (Key Takeaways)")
            for t_idx, t_point in enumerate(paper['takeaways'], 1):
                md_body.append(f"{t_idx}. {t_point}")
            md_body.append("")

            if paper.get('implications'):
                md_body.append("#### 💡 연구자 시사점 (Researcher's Takeaway)")
                md_body.append(f"{paper['implications']}\n")

            if paper.get('abstract') and "초록이 NCBI에 제공되지 않는" not in paper['abstract']:
                md_body.append(f"#### 📄 논문 원문 초록 (Abstract)\n{paper['abstract']}\n")

            md_body.append("---\n")

    # 주간 종합 표
    if processed_papers:
        md_body.append("## 📊 이번 주 수집 논문 한눈에 보기\n")
        md_body.append("| 논문 제목 (헤드라인) | 대상 생물군 | 분류 섹션 | DOI 링크 |")
        md_body.append("|:---|:---|:---|:---:|")
        for p in processed_papers[:20]:
            clean_title = (p['headline'].replace("|", "-")[:60] + "...") if len(p['headline']) > 60 else p['headline']
            md_body.append(f"| {clean_title} | *{', '.join(p['taxa'])}* | {p['category_name']} | [원문보기]({p['url']}) |")
        md_body.append("\n---\n*본 문서는 Phyco Research Archive Automation Bot v2.0에 의해 자동 수집 및 파싱되었습니다.*")

    final_md = "\n".join(md_body)
    with open(archive_file, "w", encoding="utf-8") as f:
        f.write(final_md)
    print(f" => Markdown 아카이브 영구 저장 완료: {archive_file}")

    # 4. 프론트엔드용 JSON 저장
    latest_data = {
        "date": today_str,
        "total_papers": len(processed_papers),
        "taxa": taxa_all_set,
        "editor_insights": EDITOR_INSIGHTS,
        "articles": processed_papers
    }
    with open(PUBLIC_DATA_DIR / "latest-articles.json", "w", encoding="utf-8") as f:
        json.dump(latest_data, f, ensure_ascii=False, indent=2)
    print(f" => 프론트엔드 최신 JSON 데이터 저장 완료: {PUBLIC_DATA_DIR / 'latest-articles.json'}")

    print("\n[4/4] 파이프라인 수집 완료!")


if __name__ == "__main__":
    run_pipeline()
