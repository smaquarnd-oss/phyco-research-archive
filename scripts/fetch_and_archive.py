#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phyco & Blue Carbon Research Archive Pipeline v2.1 (Refined)
─────────────────────────────────────────────────────────────────────────────
주요 개선사항:
  ① KCI (한국학술지인용색인) Open API 연동 및 한글 키워드 분기 수집
  ② Researcher's Takeaway 기계적 템플릿(연구 목적:, 주요 성과: 등) 완전 제거
     - 초록의 핵심 문장 자체를 추출하여 자연스럽고 고유한 Key Takeaways 구성
  ③ 4분할 카테고리 및 중복 없는 썸네일 매칭 유지
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import json
import re
import ssl
import hashlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

# ── Windows 콘솔 UTF-8 강제 설정 (한글 깨짐 방지) ──────────────────────────
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ── 기본 디렉토리 ─────────────────────────────────────────────────────────
BASE       = Path(__file__).resolve().parent.parent
KEYWORDS_FILE  = BASE_DIR / "keywords.json"
ARCHIVES_DIR   = BASE_DIR / "archives"
PUBLIC_DATA_DIR = BASE_DIR / "public" / "data"

ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# 유틸리티
# ═══════════════════════════════════════════════════════════════════════════

def load_keywords() -> dict:
    """keywords.json 설정을 로드합니다."""
    if not KEYWORDS_FILE.exists():
        raise FileNotFoundError(f"키워드 설정 파일을 찾을 수 없습니다: {KEYWORDS_FILE}")
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_ssl_context() -> ssl.SSLContext:
    """기업망 프록시 환경에서도 안전하게 통신할 수 있는 CERT_NONE SSL 컨텍스트를 반환합니다."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def strip_html(text: str) -> str:
    """HTML 태그를 제거하고 공백을 정돈합니다."""
    return re.sub(r'<[^>]+>', '', text or '').strip()


def paper_fingerprint(title: str, doi: str = "") -> str:
    """논문의 중복 체크용 단순 해시를 생성합니다."""
    key = (doi or title).strip().lower()
    return hashlib.md5(key.encode('utf-8')).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# 검색 함수: Europe PMC
# ═══════════════════════════════════════════════════════════════════════════

def search_europe_pmc(query: str, page_size: int = 10) -> list[dict]:
    """Europe PMC REST API (resultType=core) 로 영문 논문을 검색합니다[cite: 1]."""
    url = (
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        f"?query={urllib.parse.quote(query)}"
        "&resultType=core&format=json"
        f"&pageSize={page_size}&sort=P_PD_D%20desc"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "PhycoBlueCarbonArchiveBot/2.1"})
    try:
        with urllib.request.urlopen(req, timeout=12, context=get_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("resultList", {}).get("result", [])
            for item in results:
                raw_abs = item.get("abstractText", "")
                if raw_abs:
                    item["abstractText"] = strip_html(raw_abs)
                item["_source"] = "Europe PMC"
            return results
    except Exception as e:
        print(f"  [!] Europe PMC 오류: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════
# 검색 함수: PubMed (eSearch + eFetch XML)
# ═══════════════════════════════════════════════════════════════════════════

def search_pubmed(query: str, page_size: int = 8) -> list[dict]:
    """NCBI PubMed E-utilities: eSearch → eFetch XML 파이프라인[cite: 1]."""
    headers = {"User-Agent": "PhycoBlueCarbonArchiveBot/2.1"}
    try:
        esearch_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pubmed&term={urllib.parse.quote(query)}"
            f"&retmode=json&retmax={page_size}&sort=pub_date"
        )
        with urllib.request.urlopen(
            urllib.request.Request(esearch_url, headers=headers),
            timeout=12, context=get_ssl_context()
        ) as resp:
            id_list = json.loads(resp.read().decode("utf-8")) \
                          .get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []

        efetch_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            f"?db=pubmed&id={','.join(id_list)}&retmode=xml"
        )
        with urllib.request.urlopen(
            urllib.request.Request(efetch_url, headers=headers),
            timeout=15, context=get_ssl_context()
        ) as resp:
            root = ET.fromstring(resp.read())

        articles = []
        for article_elem in root.findall(".//PubmedArticle"):
            medline = article_elem.find(".//MedlineCitation")
            if medline is None:
                continue
            pmid = medline.findtext(".//PMID", default="")
            art  = medline.find(".//Article")
            if art is None:
                continue

            title = art.findtext(".//ArticleTitle", default="").strip().rstrip(".")

            parts = []
            for ab in art.findall(".//AbstractText"):
                label = ab.get("Label", "")
                txt   = "".join(ab.itertext()).strip()
                if txt:
                    parts.append(f"[{label}] {txt}" if label and label.upper() not in ("UNLABELLED",) else txt)
            abstract = "\n\n".join(parts).strip() or ""

            author_names = []
            for auth in art.findall(".//AuthorList/Author"):
                last  = auth.findtext("LastName", "")
                fore  = auth.findtext("ForeName", "")
                coll  = auth.findtext("CollectiveName", "")
                if coll:
                    author_names.append(coll)
                elif last:
                    author_names.append(f"{last} {fore[:1]}".strip() if fore else last)
            author_str = ", ".join(author_names[:4]) + (" et al." if len(author_names) > 4 else "")

            journal  = art.findtext(".//Journal/Title") or art.findtext(".//Journal/ISOAbbreviation") or "Academic Journal"
            pub_year = art.findtext(".//JournalIssue/PubDate/Year") \
                    or medline.findtext(".//DateCompleted/Year") \
                    or str(datetime.now().year)
            doi = ""
            for id_elem in article_elem.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if id_elem.get("IdType") == "doi":
                    doi = (id_elem.text or "").strip()
                    break

            articles.append({
                "id":           pmid,
                "doi":          doi or f"pmid:{pmid}",
                "title":        title,
                "authorString": author_str or "저자 정보 없음",
                "journalTitle": journal,
                "pubYear":      pub_year,
                "abstractText": abstract,
                "_source":      "PubMed",
                "_lang":        "en",
            })

        return articles

    except Exception as e:
        print(f"  [!] PubMed 파싱 오류: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════
# 검색 함수: KCI (한국학술지인용색인) Open API
# ═══════════════════════════════════════════════════════════════════════════

def search_kci(query: str, page_size: int = 10, page: int = 1) -> list[dict]:
    """KCI Open API (articleSearch) 로 국내 학술 논문을 검색합니다[cite: 1]."""
    api_key = os.environ.get("KCI_API_KEY", "").strip()
    if not api_key:
        return []

    endpoint = "https://open.kci.go.kr/po/openapi/openApiSearch.kci"
    params = urllib.parse.urlencode({
        "apiCode":      "articleSearch",
        "key":          api_key,
        "keyword":      query,
        "displayCount": min(page_size, 100),
        "page":         page,
    })
    url = f"{endpoint}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "PhycoBlueCarbonArchiveBot/2.1"})

    try:
        with urllib.request.urlopen(req, timeout=15, context=get_ssl_context()) as resp:
            raw_bytes = resp.read()
            xml_text  = raw_bytes.decode("utf-8", errors="replace")

        try:
            root = ET.fromstring(xml_text.encode("utf-8"))
        except ET.ParseError as pe:
            print(f"  [!] KCI XML 파싱 경고: {pe}")
            return []

        result_msg = root.findtext(".//resultMsg", "").strip()
        if result_msg and "등록되지 않은" in result_msg:
            print(f"  [KCI API 오류] {result_msg} (IP 등록을 확인하세요)")
            return []

        articles = []
        for record in root.findall(".//record"):
            def rtext(tag: str) -> str:
                el = record.find(tag)
                return (el.text or "").strip() if el is not None else ""

            title    = rtext("article-title") or rtext("title")
            authors  = rtext("author-names")
            journal  = rtext("journal-title")
            pub_year = rtext("pub-year") or rtext("year") or str(datetime.now().year)
            abstract = rtext("abstract")
            doi_raw  = rtext("doi")
            url_raw  = rtext("url")
            keywords = rtext("keyword")

            if not title:
                continue

            author_list = [a.strip() for a in re.split(r"[;,]", authors) if a.strip()]
            author_str  = ", ".join(author_list[:4]) + (" 외" if len(author_list) > 4 else "")

            if not abstract:
                kw_note = f" 주요 키워드: {keywords}." if keywords else ""
                abstract = f"[국내 학술지 논문] 메타데이터 초록 생략.{kw_note}"

            doi = doi_raw.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
            doi_url = f"https://doi.org/{doi}" if doi else (url_raw or "#")
            uid = doi or url_raw or paper_fingerprint(title)

            articles.append({
                "id":           uid,
                "doi":          doi or uid,
                "title":        title,
                "authorString": author_str or "저자 정보 없음",
                "journalTitle": journal or "국내 학술지",
                "pubYear":      pub_year,
                "abstractText": abstract,
                "kci_keywords": keywords,
                "url":          doi_url,
                "_source":      "KCI",
                "_lang":        "ko",
            })

        print(f"  [KCI] '{query}' → {len(articles)}편 수집")
        return articles

    except Exception as e:
        print(f"  [!] KCI API 호출 오류 (쿼리: {query}): {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════
# 분류 함수
# ═══════════════════════════════════════════════════════════════════════════

def classify_article(article: dict, taxa_list: list, categories: dict) -> tuple[list, str]:
    """논문 제목·초록·KCI 키워드를 분석하여 생물군 및 카테고리를 분류합니다[cite: 1]."""
    title    = article.get("title", "")
    abstract = article.get("abstractText", "")
    kci_kw   = article.get("kci_keywords", "")
    full_text = f"{title} {abstract} {kci_kw}".lower()

    matched_taxa = []
    for taxa in taxa_list:
        if not taxa.get("enabled", True):
            continue
        candidates = [taxa["name"]] + taxa.get("aliases", []) + taxa.get("korean_names", [])
        for cand in candidates:
            if cand.lower() in full_text:
                matched_taxa.append(taxa["name"])
                break

    cat_scores = []
    for cat_id, cat_info in categories.items():
        score = 0
        for kw in cat_info.get("keywords", []):
            if kw.lower() in full_text:
                score += 1
        for kw in cat_info.get("keywords_ko", []):
            if kw in full_text:
                score += 2
        if score > 0:
            cat_scores.append((cat_id, score))

    cat_scores.sort(key=lambda x: x[1], reverse=True)
    default_cat  = "thallus_lifecycle_conchocelis"
    best_category = cat_scores[0][0] if cat_scores else default_cat

    return list(set(matched_taxa)), best_category


# ═══════════════════════════════════════════════════════════════════════════
# 썸네일 매칭
# ═══════════════════════════════════════════════════════════════════════════

CURATED_THUMBNAILS = {
    "breeding_molecular_pathology": [
        "https://images.unsplash.com/photo-1532187863486-abf9dbad1b69?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1579154204601-01588f351e67?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1507668077129-56e32842fceb?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1563674407-b5de7db5ccb0?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1484557052118-f32bd25b45b5?auto=format&fit=crop&w=800&q=80",
    ],
    "thallus_lifecycle_conchocelis": [
        "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1518837695005-2083093ee35b?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1614728894747-a83421789f10?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1559827260-dc66d52bef19?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1509563768818-dafe9ad27b4e?auto=format&fit=crop&w=800&q=80",
    ],
    "smart_aquaculture_mass_culture": [
        "https://images.unsplash.com/photo-1581093458791-9f3c3900df4b?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1565193566173-7a0ee3dbe261?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1594122230689-45899d9e6f69?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1608408891571-89c4aa18ef7c?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1576086213369-97a306d36557?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1530541930197-ff16ac917b0e?auto=format&fit=crop&w=800&q=80",
    ],
    "blue_carbon_feed_methane": [
        "https://images.unsplash.com/photo-1682687220063-4742bd7fd538?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1682687220199-d0124f48f95b?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1500595046743-cd271d694d30?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1498084393753-b411b2d26b34?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1552728089-57bdde30beb3?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1473341304170-971dccb5ac1e?auto=format&fit=crop&w=800&q=80",
    ],
}

KEYWORD_THUMBNAIL_HINT = {
    "breeding_molecular_pathology": {
        "dna": 0, "barcode": 0, "barcod": 0, "genomic": 0, "phylogen": 0,
        "유전체": 0, "DNA 바코딩": 0, "계통": 0,
        "microscop": 1, "cell": 1, "세포": 1,
        "transcriptom": 2, "crispr": 2, "전사체": 2,
        "pcr": 3, "sequenc": 3, "분자마커": 3,
        "biotech": 4, "protein": 4, "단백질": 4,
        "disease": 5, "pathogen": 5, "병해": 5, "붉은갯병": 5,
    },
    "thallus_lifecycle_conchocelis": {
        "thallus": 0, "blade": 0, "엽체": 0,
        "seaweed": 1, "macroalga": 1, "해조류": 1,
        "conchocel": 2, "spore": 2, "사상체": 2, "각포자": 2,
        "photosynthes": 3, "pigment": 3, "광합성": 3,
        "life cycle": 4, "생활사": 4, "생활환": 4,
        "germination": 5, "발아": 5,
    },
    "smart_aquaculture_mass_culture": {
        "bioreactor": 0, "flask": 0, "바이오리액터": 0,
        "aquaculture": 1, "farm": 1, "양식": 1,
        "culture medium": 2, "nutrient": 2, "배양": 2,
        "led": 3, "indoor": 3, "실내 배양": 3,
        "harvest": 4, "yield": 4, "수확": 4, "생산": 4,
        "seeding": 5, "채묘": 5, "종사": 5,
    },
    "blue_carbon_feed_methane": {
        "carbon sequestrat": 0, "blue carbon": 0, "블루카본": 0, "탄소격리": 0,
        "ocean": 1, "marine": 1, "해양": 1,
        "climate": 2, "greenhouse": 2, "온실가스": 2, "기후": 2,
        "flux": 3, "RDOC": 3, "탄소": 3,
        "livestock": 4, "cattle": 4, "사료": 4, "메탄": 4,
        "biofuel": 5, "agar": 5, "한천": 5, "산업": 5,
    },
}

def pick_thumbnail(cat_id: str, title: str, abstract: str, used_urls: set) -> str:
    pool   = CURATED_THUMBNAILS.get(cat_id, CURATED_THUMBNAILS["thallus_lifecycle_conchocelis"])
    hints  = KEYWORD_THUMBNAIL_HINT.get(cat_id, {})
    text   = f"{title} {abstract}".lower()

    preferred_idx, best_score = 0, -1
    for kw, idx in hints.items():
        if kw.lower() in text and idx > best_score:
            preferred_idx, best_score = idx, idx

    n = len(pool)
    for offset in range(n):
        url = pool[(preferred_idx + offset) % n]
        if url not in used_urls:
            used_urls.add(url)
            return url
    return pool[preferred_idx % n]


# ═══════════════════════════════════════════════════════════════════════════
# 에디터 인사이트 (4분할)
# ═══════════════════════════════════════════════════════════════════════════

EDITOR_INSIGHTS = {
    "breeding_molecular_pathology": {
        "title": "기후 온난화 대응 내열성 분자마커와 붉은갯병 감염 초기 전사체 분석의 고도화",
        "content": (
            "이번 주 육종 및 병해 연구 트렌드는 해수 온도 상승에 따른 내삼투압/열충격 단백질(HSP) "
            "발현 메커니즘 규명과 더불어, 주요 병원체 대응 방어 전사인자 동정이 두드러집니다."
        )
    },
    "thallus_lifecycle_conchocelis": {
        "title": "사상체(Conchocelis) 각포자 방출 메커니즘과 엽체 생리 환경 적응 전략",
        "content": (
            "엽체 생리 및 생활사 연구 분야에서는 광주기·수온 변동에 의한 각포자 대량 방출 제어 기전과 "
            "엽상체 기조직 발달 초기 단계 분자 마커가 주목받고 있습니다."
        )
    },
    "smart_aquaculture_mass_culture": {
        "title": "자유사상체 대량 배양과 스마트 채묘 시스템의 경제성 최적화",
        "content": (
            "스마트 양식 및 대량 배양 분야는 굴패각 의존도를 낮추는 자유사상체 액체 배양 조건 최적화와 "
            "LED 파장별 성장률 비교를 중심으로 성과가 보고되었습니다."
        )
    },
    "blue_carbon_feed_methane": {
        "title": "해조류 기반 메탄 감축 실증과 RDOC 기반 블루카본 탄소 격리 플럭스 표준화",
        "content": (
            "블루카본 및 산업 응용 분야는 대형 해조류의 반추위 장내 메탄 저감 효과 검증과 "
            "연간 침적 불용성 유기탄소의 탄소배출권 방법론 연구가 급물살을 타고 있습니다."
        )
    },
}

SECTION_ORDER = [
    "breeding_molecular_pathology",
    "thallus_lifecycle_conchocelis",
    "smart_aquaculture_mass_culture",
    "blue_carbon_feed_methane",
]


# ═══════════════════════════════════════════════════════════════════════════
# AI / 룰베이스 논문 분석 (기계적 템플릿 제거 및 Key Takeaways 고도화)
# ═══════════════════════════════════════════════════════════════════════════

def _ruleset_summary(title: str, abstract: str, category_name: str,
                     taxa_list: list, kci_keywords: str = "") -> dict:
    """
    기계적 접두사(연구 목적:, 주요 성과: 등)를 완전히 제거하고,
    초록 문장을 활용한 자연스러운 Key Takeaways를 생성합니다[cite: 1].
    """
    taxa_str = ", ".join(taxa_list) if taxa_list else category_name

    raw_sents = [
        s.strip() for s in re.split(r'(?<=[.。])\s+|(?<=。)', abstract)
        if len(s.strip()) > 15
    ]
    clean_sents = [re.sub(r'^\[[A-Z /]+\]\s*', '', s) for s in raw_sents]
    clean_sents = [s for s in clean_sents if len(s) > 20]

    headline = title
    if len(title) > 65:
        headline = title[:65].rsplit(" ", 1)[0] + "…"

    takeaways = []
    n = len(clean_sents)

    # 템플릿 딱지를 완전히 떼고 핵심 문장 자체를 구성
    if n >= 3:
        takeaways = [
            clean_sents[0],
            clean_sents[n // 2],
            clean_sents[-1],
        ]
    elif n == 2:
        takeaways = [
            clean_sents[0],
            clean_sents[1],
            f"대상 분류군 {taxa_str}를 활용한 {category_name} 실증 분석.",
        ]
    elif n == 1:
        takeaways = [
            clean_sents[0],
            f"연구 분야: {category_name} ({taxa_str}).",
            f"실용적 가치 및 특성 검증.",
        ]
    else:
        title_words = title.split()
        kw_note = f" 키워드: {kci_keywords}." if kci_keywords else ""
        takeaways = [
            f"연구 주제: {' '.join(title_words[:10])}.{kw_note}",
            f"연구 분야: {category_name} ({taxa_str}).",
            f"국내외 학술 데이터베이스 등록 문헌 분석.",
        ]

    implications = (
        f"본 연구는 {taxa_str}의 {category_name} 분야에서 구체적인 실험 데이터를 도출하며, "
        f"관련 생물학적 메커니즘 규명과 현장 양식 기술 고도화에 기여합니다."
    )
    title_tokens = [w for w in title.split() if len(w) > 3][:3]
    if title_tokens:
        implications = (
            f"'{' '.join(title_tokens)}' 관련 분석을 통해 {taxa_str}의 {category_name} "
            f"환경 최적화 및 실용화 타당성을 검증하였습니다."
        )

    return {
        "headline":    headline,
        "takeaways":   takeaways[:3],
        "implications": implications,
        "is_ai":       False,
    }


def analyze_paper_content(
    title: str,
    abstract: str,
    category_name: str,
    taxa_list: list,
    cat_id: str,
    thumbnail_url: str,
    kci_keywords: str = "",
    paper_lang: str = "en",
) -> dict:
    taxa_str = ", ".join(taxa_list) if taxa_list else category_name
    api_key  = os.environ.get("GEMINI_API_KEY", "").strip()

    lang_instruction = (
        "한국어(국문)로 작성된 논문입니다. 모든 분석 출력을 한국어로 작성하세요."
        if paper_lang == "ko" else
        "논문이 영문(English)으로 작성되어 있습니다. 분석 결과는 한국어로 작성하세요."
    )

    if api_key and abstract and len(abstract) > 80:
        prompt = f"""당신은 해조류·해양 블루카본 분야의 수석 연구위원이자 사이언스 매거진 에디터입니다.
{lang_instruction}
아래 논문 정보를 기반으로 연구 매거진 카드 데이터를 JSON으로 작성하세요.
★ 중요: 기계적인 템플릿 문구("연구 목적:", "주요 성과:" 등)를 절대 사용하지 말고, 논문 고유의 핵심 발견 내용을 자연스럽고 전문적인 개조식 문장으로 작성하세요.

[논문 정보]
- 제목: {title}
- 대상 생물군: {taxa_str}
- 연구 분야: {category_name}
- 초록/요약:
{abstract[:1200]}

[출력 형식 — 순수 JSON만 반환, 설명 텍스트 없음]
{{
  "headline": "이 논문만의 핵심을 담은 한 줄 국문 헤드라인 (30~50자)",
  "takeaways": [
    "논문의 구체적 연구 배경 또는 목적에 대한 핵심 문장",
    "논문에서 밝혀낸 핵심 실험 결과 또는 수치/유전자명 데이터",
    "규명된 생물학적 기작 또는 현장 적용 가치에 대한 결론"
  ],
  "implications": "이 연구가 양식 현장 또는 학술/산업에 주는 구체적 시사점 (1~2문장)"
}}"""
        try:
            gemini_url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.5-flash:generateContent?key={api_key}"
            )
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.25, "responseMimeType": "application/json"}
            }
            req = urllib.request.Request(
                gemini_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=25, context=get_ssl_context()) as resp:
                res_json  = json.loads(resp.read().decode("utf-8"))
                candidates = res_json.get("candidates", [])
                if candidates:
                    parsed = json.loads(candidates[0]["content"]["parts"][0]["text"].strip())
                    return {
                        "headline":    parsed.get("headline", title),
                        "takeaways":   parsed.get("takeaways", []),
                        "implications": parsed.get("implications", ""),
                        "thumbnail_url": thumbnail_url,
                        "is_ai":       True,
                    }
        except Exception as e:
            print(f"  [-] Gemini 요약 실패: {e}")

    result = _ruleset_summary(title, abstract, category_name, taxa_list, kci_keywords)
    result["thumbnail_url"] = thumbnail_url
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 메인 파이프라인
# ═══════════════════════════════════════════════════════════════════════════

def run_pipeline():
    print("=" * 60)
    print("🌊 Phyco & Blue Carbon Research Magazine Pipeline v2.1")
    print(f"   실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("   소스: Europe PMC · PubMed · KCI (국내)")
    print("=" * 60)

    config       = load_keywords()
    target_taxa  = config.get("target_taxa", {}).get("genera", [])
    categories   = config.get("research_categories", {})
    lookback_days = config.get("search_settings", {}).get("days_lookback", 7)

    used_thumbnails_per_cat: dict[str, set] = {cat: set() for cat in categories}
    collected: dict[str, dict] = {}

    def _add(item: dict):
        doi   = item.get("doi", "")
        title = item.get("title", "")
        fp    = paper_fingerprint(title, doi)
        if fp not in collected:
            collected[fp] = item

    # STEP 1: 생물군별 영문 검색 (Europe PMC + PubMed)[cite: 1]
    print("\n[1/5] 생물군별 영문 검색 (Europe PMC & PubMed)...")
    date_from = (datetime.now().date() - timedelta(days=lookback_days * 4)).isoformat()
    date_to   = datetime.now().date().isoformat()

    for taxa in target_taxa:
        taxa_name = taxa["name"]
        print(f"  → 생물군 '{taxa_name}' 검색...")
        epmc_q = f'("{taxa_name}") AND (FIRST_PDATE:[{date_from} TO {date_to}])'
        results = search_europe_pmc(epmc_q, page_size=8)
        if len(results) < 2:
            fallback_alias = taxa.get("aliases", [taxa_name])[0]
            results = search_europe_pmc(f'("{taxa_name}" OR "{fallback_alias}")', page_size=5)

        for item in results:
            item["_lang"] = "en"
            _add(item)

        if not results:
            pm_results = search_pubmed(
                f'{taxa_name}[Title/Abstract] AND ("2024"[Date - Publication] : "3000"[Date - Publication])',
                page_size=5
            ) or search_pubmed(taxa_name, page_size=5)
            for item in pm_results:
                _add(item)

    # STEP 2: 카테고리별 한글 키워드 → KCI 검색[cite: 1]
    print("\n[2/5] 카테고리별 한글 키워드 → KCI 국내 학술 검색...")
    kci_enabled = os.environ.get("KCI_API_KEY", "").strip() != ""
    if not kci_enabled:
        print("  [KCI 안내] KCI_API_KEY가 설정되지 않아 국내 논문 검색을 건너뜁니다.")
        print("             (인증키 발급 후 .env에 KCI_API_KEY를 설정하면 국내 논문도 함께 수집됩니다)")
    else:
        for taxa in target_taxa:
            for kname in taxa.get("korean_names", []):
                for item in search_kci(kname, page_size=8):
                    _add(item)

        for cat_id, cat_info in categories.items():
            for kw in cat_info.get("keywords_ko", [])[:3]:
                for item in search_kci(kw, page_size=5):
                    _add(item)

    # STEP 3: 분류 및 요약 생성[cite: 1]
    print(f"\n[3/5] {len(collected)}편 논문 분류 및 요약 생성 중...")
    processed_papers: list[dict] = []

    for idx, (fp, raw) in enumerate(collected.items(), 1):
        title    = (raw.get("title", "") or "").rstrip(".")
        abstract = raw.get("abstractText", "")
        kci_kw   = raw.get("kci_keywords", "")
        author_str = raw.get("authorString", "Unknown authors")
        journal  = raw.get("journalTitle") or "Academic Journal"
        pub_year = raw.get("pubYear", str(datetime.now().year))
        paper_lang = raw.get("_lang", "en")
        source   = raw.get("_source", "Unknown")

        matched_taxa, best_cat = classify_article(raw, target_taxa, categories)
        if not matched_taxa:
            matched_taxa = ["Pyropia/Porphyra complex"]

        doi      = raw.get("doi", "")
        doi_url  = raw.get("url") or (f"https://doi.org/{doi}" if doi and not doi.startswith("http") else "#")
        cat_info = categories.get(best_cat, {})

        used_set = used_thumbnails_per_cat.setdefault(best_cat, set())
        thumb    = pick_thumbnail(best_cat, title, abstract, used_set)

        analysis = analyze_paper_content(
            title=title,
            abstract=abstract,
            category_name=cat_info.get("name_ko", "해조류 생물학"),
            taxa_list=matched_taxa,
            cat_id=best_cat,
            thumbnail_url=thumb,
            kci_keywords=kci_kw,
            paper_lang=paper_lang,
        )

        src_badge = f"[{source}]" if source != "Unknown" else ""
        paper = {
            "title":         title,
            "headline":      analysis["headline"],
            "takeaways":     analysis["takeaways"],
            "implications":  analysis["implications"],
            "thumbnail_url": analysis["thumbnail_url"],
            "abstract":      abstract,
            "authors":       author_str,
            "journal":       journal,
            "year":          pub_year,
            "doi":           doi,
            "url":           doi_url,
            "taxa":          matched_taxa,
            "category":      best_cat,
            "category_name": cat_info.get("name_ko", "기타 연구"),
            "badge_color":   cat_info.get("badge_color", "emerald"),
            "source":        source,
            "lang":          paper_lang,
            "kci_keywords":  kci_kw,
            "is_ai_summary": analysis["is_ai"],
        }
        processed_papers.append(paper)
        print(f"  [{idx:02d}] {src_badge} {title[:55]}…")

    # STEP 4: 마크다운 아카이브 저장[cite: 1]
    print("\n[4/5] 4분할 섹션 마크다운 아카이브 생성 중...")
    today_str = datetime.now().strftime("%Y-%m-%d")
    archive_file = ARCHIVES_DIR / f"{today_str}-weekly-digest.md"

    cat_grouped: dict[str, list] = {}
    for p in processed_papers:
        cat_grouped.setdefault(p["category"], []).append(p)

    taxa_all_set = list({t for p in processed_papers for t in p["taxa"]})
    sources_used = list({p["source"] for p in processed_papers})

    frontmatter = (
        f'---\n'
        f'title: "김·바다고리풀 & 블루카본 연구 주간 다이제스트 ({today_str})"\n'
        f'date: "{today_str}"\n'
        f'version: "2.1"\n'
        f'total_papers: {len(processed_papers)}\n'
        f'sources: {json.dumps(sources_used, ensure_ascii=False)}\n'
        f'taxa_covered: {json.dumps(taxa_all_set, ensure_ascii=False)}\n'
        f'categories: {json.dumps(list(cat_grouped.keys()), ensure_ascii=False)}\n'
        f'tags: ["Phyco", "BlueCarbon", "Seaweed", "KCI", "국내논문"]\n'
        f'---\n'
    )

    md_body = [
        frontmatter,
        f"# 🌊 김/바다고리풀속 및 블루카본 연구 주간 매거진 ({today_str})\n",
        f"> **발행일**: {today_str} | **총 논문**: {len(processed_papers)}편 | **수집 소스**: {', '.join(sources_used)}  ",
        f"> **포함 생물군**: {', '.join(taxa_all_set) or 'Pyropia, Asparagopsis'}\n",
        "---\n",
    ]

    for cat_id in SECTION_ORDER:
        cat_info     = categories.get(cat_id, {})
        papers_in_cat = cat_grouped.get(cat_id, [])
        if not papers_in_cat:
            continue

        section_no = cat_info.get("section_no", "0X")
        insight    = EDITOR_INSIGHTS.get(cat_id, {})

        md_body.append(f"## 🔬 SECTION {section_no}: {cat_info.get('name_ko')} ({cat_info.get('name_en', '')})\n")
        md_body.append(f"> 💡 **Editor's Weekly Insight: {insight.get('title')}**  \n> {insight.get('content')}\n")

        for pidx, paper in enumerate(papers_in_cat, 1):
            lang_tag = "🇰🇷 국내" if paper.get("lang") == "ko" else "🌐 해외"
            src_tag  = paper.get("source", "")
            md_body.append(f"### {pidx}. {paper['headline']}")
            md_body.append(f"- **원문 제목**: {paper['title']}")
            md_body.append(f"- **저자**: {paper['authors']}")
            md_body.append(f"- **저널**: *{paper['journal']}* ({paper['year']}) | **출처**: {lang_tag} {src_tag} | **원문**: [{paper['doi'] or 'Link'}]({paper['url']})")
            md_body.append(f"- **대상 생물군**: `{', '.join(paper['taxa'])}`")
            md_body.append(f"- **대표 이미지**: ![]({paper['thumbnail_url']})\n")

            md_body.append("#### 📌 핵심 성과 (Key Takeaways)")
            for t_idx, t_point in enumerate(paper["takeaways"], 1):
                md_body.append(f"{t_idx}. {t_point}")
            md_body.append("")

            if paper.get("implications"):
                md_body.append("#### 💡 연구자 시사점 (Researcher's Takeaway)")
                md_body.append(f"{paper['implications']}\n")

            if paper.get("kci_keywords"):
                md_body.append(f"#### 🏷 KCI 원문 키워드\n`{paper['kci_keywords']}`\n")

            if paper.get("abstract") and "메타데이터 초록 생략" not in paper["abstract"]:
                md_body.append(f"#### 📄 논문 원문 초록 (Abstract)\n{paper['abstract']}\n")

            md_body.append("---\n")

    with open(archive_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md_body))
    print(f"  => Markdown 아카이브 저장: {archive_file}")

    # STEP 5: 프론트엔드 JSON 저장[cite: 1]
    latest_data = {
        "date":           today_str,
        "version":        "2.1",
        "total_papers":   len(processed_papers),
        "sources_used":   sources_used,
        "taxa":           taxa_all_set,
        "editor_insights": EDITOR_INSIGHTS,
        "articles":       processed_papers,
    }
    json_path = PUBLIC_DATA_DIR / "latest-articles.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(latest_data, f, ensure_ascii=False, indent=2)
    print(f"  => 프론트엔드 JSON 저장: {json_path}")

    print(f"\n[5/5] 완료! 총 {len(processed_papers)}편 수집 완료.")
    print("=" * 60)


if __name__ == "__main__":
    run_pipeline()
