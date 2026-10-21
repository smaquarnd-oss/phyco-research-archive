#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phyco & Blue Carbon Research Archive Pipeline (Python 3.11+)
─────────────────────────────────────────────────────────────────────────────
[핵심 해결 과제 및 구현 명세]
  1. 깡통 논문(초록 미제공/200자 미만) 원천 배제 (Drop filtering)
     - 실제 텍스트가 풍부한 200자 이상의 초록을 보유한 논문만 엄선 수집.
     - 가짜 템플릿 문장("연구 목적:", "실험 분석:" 등) 조합을 철저히 금지.
  2. 국내 학술지 및 한국어 논문 수집 로직 (Crossref KCI & KCI OAI-PMH)
     - Crossref API (filter=has-abstract:true) 기반 국문 논문 및 KCI 등재지 수집.
     - KCI OAI-PMH 프로토콜을 통한 색인 지연 누락 없는 넉넉한 기간별 대량 하베스팅.
  3. 네트워크 안정성 확보 (HTTP 429 / 503 에러 대응)
     - Exponential Backoff 기반 최대 3회 재시도 `fetch_with_retry` 전면 적용.
  4. 정밀한 키워드 필터링 (비전문 분야 유입 차단)
     - 법학, 토양학, 일반 농업 등 차단: 해조류/수산 필수 전문 키워드 도메인 검증 통과 필수.
  5. 안전한 카테고리 매칭 및 썸네일 고정
     - `keywords.json`의 `research_categories` 포맷(dict/list/str) 무관 방어 로직.
     - 썸네일은 common.assign_unique_thumbnails 로 한 호 안에서 중복 없이 배정.
  6. 동적 요약 및 인사이트 생성 (Gemini ➔ Claude ➔ 룰베이스 하이브리드)
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import json
import re
import ssl
import time
import random
import hashlib
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ── Windows 콘솔 및 입출력 UTF-8 강제 설정 ───────────────────────────────────
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402  (fetch / build 공통 로직)
    assign_unique_thumbnails,
    clean_summary,
    extractive_summary,
    split_into_sentences,
    strip_html,
)

# ── 경로 설정 ─────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).resolve().parent.parent
KEYWORDS_FILE   = BASE_DIR / "keywords.json"
ARCHIVES_DIR    = BASE_DIR / "archives"
PUBLIC_DATA_DIR = BASE_DIR / "public" / "data"

ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 환경변수 및 유틸리티
# ═══════════════════════════════════════════════════════════════════════════

def load_env_file() -> None:
    """프로젝트 루트의 .env 파일을 자동으로 감지하여 os.environ에 주입합니다."""
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = re.sub(r"\s+#.*$", "", v)  # 같은 줄 주석 제거 (예: AI_PROVIDER=claude   # 설명)
                        v = v.strip().strip('"').strip("'")
                        if k and not os.environ.get(k):
                            os.environ[k] = v
        except Exception as e:
            print(f"  [!] .env 파일 파싱 경고: {e}")

load_env_file()


def load_keywords() -> dict:
    """keywords.json 설정을 로드합니다."""
    if not KEYWORDS_FILE.exists():
        raise FileNotFoundError(f"키워드 설정 파일을 찾을 수 없습니다: {KEYWORDS_FILE}")
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


_SSL_CONTEXT: Optional[ssl.SSLContext] = None


def get_ssl_context() -> ssl.SSLContext:
    """
    인증서 검증을 켠 SSL 컨텍스트.
    Windows 인증서 저장소로는 NCBI(PubMed) 인증서 체인 검증이 실패하는 PC가 있어
    certifi 인증서 묶음을 우선 사용합니다 (requirements.txt 에 포함).
    """
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        try:
            import certifi
            _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            print("  [!] certifi 미설치 → 시스템 인증서 사용 (pip install -r requirements.txt 권장)")
            _SSL_CONTEXT = ssl.create_default_context()
    return _SSL_CONTEXT


def paper_fingerprint(
    title: str,
    doi: str = "",
    pmid: str = ""
) -> str:
    """DOI, PMID, 제목 순서로 논문 식별자를 생성합니다."""
    if doi:
        key = f"doi:{doi.strip().lower()}"
    elif pmid:
        key = f"pmid:{pmid.strip()}"
    else:
        normalized_title = re.sub(r"\s+", " ", title).strip().lower()
        key = f"title:{normalized_title}"

    return hashlib.md5(key.encode("utf-8")).hexdigest()

CACHE_FILE = BASE_DIR / "summary_cache.json"

def load_summary_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_summary_cache(cache: dict) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [!] 캐시 저장 경고: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# 2. 네트워크 요청 (Exponential Backoff 재시도 함수)
# ═══════════════════════════════════════════════════════════════════════════

def fetch_with_retry(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    max_retries: int = 3,
    timeout: int = 15
) -> Optional[str]:
    req_headers = {
        "User-Agent": "PhycoResearchBot/3.0 (https://phyco-magazine.vercel.app; mailto:archive@phyco-magazine.org)",
        "Accept": "application/json, text/xml, */*"
    }
    if headers:
        req_headers.update(headers)

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout, context=get_ssl_context()) as resp:
                raw_bytes = resp.read()
                try:
                    return raw_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    return raw_bytes.decode('euc-kr', errors='replace')

        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504) and attempt < max_retries - 1:
                sleep_sec = (2 ** attempt) + random.uniform(0.8, 1.8)
                print(f"  [재시도 안내] HTTP {e.code} 감지 -> {sleep_sec:.1f}초 후 재시도 ({attempt + 1}/{max_retries})...")
                time.sleep(sleep_sec)
            else:
                print(f"  [!] HTTP 요청 실패 ({e.code}): {url[:70]}...")
                return None

        except (urllib.error.URLError, TimeoutError, ConnectionResetError) as e:
            if attempt < max_retries - 1:
                sleep_sec = (2 ** attempt) + 1.0
                print(f"  [재시도 안내] 네트워크 지연({e}) -> {sleep_sec:.1f}초 후 재시도...")
                time.sleep(sleep_sec)
            else:
                print(f"  [!] 통신 에러: {e}")
                return None

        except Exception as e:
            print(f"  [!] 예외 발생 ({url[:50]}...): {e}")
            return None

    return None


# ═══════════════════════════════════════════════════════════════════════════
# 3. 깡통 논문 배제 & 전문 도메인 검증 필터
# ═══════════════════════════════════════════════════════════════════════════

MIN_ABSTRACT_LENGTH = 200

STRONG_DOMAIN_KEYWORDS = [
    "pyropia",
    "porphyra",
    "neopyropia",
    "neoporphyra",
    "phycocalidia",
    "conchocelis",
    "conchospore",
    "seaweed aquaculture",
    "seaweed breeding",
    "nori",
    "laver",
    "김 양식",
    "김 육종",
    "김 품종",
    "김 종자",
    "김 사상체",
    "김 각포자",
    "사상체",  # "사상체질"(한의학)은 _keyword_hit 에서 제외
    "각포자",
    "각포자낭",
    "콘코셀리스",
    "해조류 양식",
    "해조류 육종",
    "asparagopsis",
    "바다고리풀",
    "방사무늬김",
    "잇바디돌김",
]

GENERAL_DOMAIN_KEYWORDS = [
    "seaweed",
    "macroalgae",
    "seaweed farming",
    "blue carbon",
    "해조류",  # "해조" 만 쓰면 "위해조직"·"해조신문" 에 걸림
]

def is_valid_abstract(abstract: Optional[str]) -> bool:
    """초록의 최소 길이와 기본적인 품질을 검증합니다."""
    if not abstract:
        return False

    clean = strip_html(abstract)

    if len(clean) < MIN_ABSTRACT_LENGTH:
        return False

    sentences = split_into_sentences(clean)

    if len(sentences) < 2:
        return False

    dummy_patterns = [
        "no abstract",
        "abstract not available",
        "초록이 없습니다",
        "메타데이터 초록 생략",
    ]

    if any(p in clean.lower() for p in dummy_patterns):
        return False

    return True


def _keyword_hit(kw: str, text: str) -> bool:
    """영문 키워드는 단어 시작 경계를 요구(laver ≠ slavery, nori ≠ minority), 한글은 부분 일치."""
    kw = kw.lower()
    if kw.isascii():
        return re.search(r"\b" + re.escape(kw), text) is not None
    if kw == "사상체":
        return re.search(r"사상체(?!질)", text) is not None
    return kw in text


# "연관 연구"(5번째 섹션)로 받아주는 넓은 해조류 키워드. 미세조류만 다루는 논문은 걸리지 않도록
# 대형 해조류를 가리키는 말만 넣었습니다.
RELATED_DOMAIN_KEYWORDS = [
    "kelp", "red alga", "brown alga", "rhodophyt", "phaeophyc", "intertidal alga",
    "ulva", "sargassum", "saccharina", "undaria", "gracilaria", "ecklonia", "ishige",
    "fucoidan", "phlorotannin",
    # agar(→agarose gel)·carrageenan(염증 모델)·alginate(의료용 하이드로젤)는 다른 분야 논문을 끌어와서 제외
    "미역", "다시마", "모자반", "파래", "우뭇가사리", "홍조류", "갈조류", "곰피", "감태",
    "후코이단", "블루카본",
]


def relevance_tier(title: str, abstract: str, keywords: str = "") -> Optional[str]:
    """
    'core'    : 김속·바다고리풀·해조류 양식 등 핵심 키워드 → 4개 본 섹션
    'related' : 일반 해조류 키워드만 → 5번째 "연관 연구" 섹션 (호당 상한 있음)
    None      : 수록하지 않음
    """
    combined = f"{title} {abstract} {keywords}".lower()
    if any(_keyword_hit(kw, combined) for kw in STRONG_DOMAIN_KEYWORDS):
        return "core"
    # 연관 연구: 제목에 해조류 키워드가 있거나, 서로 다른 키워드가 2개 이상
    # (초록에 "seaweed 유래 섬유" 처럼 한 번 스치듯 나온 의학 논문 등을 거르기 위해)
    broad = GENERAL_DOMAIN_KEYWORDS + RELATED_DOMAIN_KEYWORDS
    title_l = (title or "").lower()
    if any(_keyword_hit(kw, title_l) for kw in broad):
        return "related"
    if sum(1 for kw in broad if _keyword_hit(kw, combined)) >= 2:
        return "related"
    return None


def is_domain_relevant(title: str, abstract: str, keywords: str = "") -> bool:
    """해조류 관련 논문이면 True (핵심·연관 모두). 등급은 relevance_tier 로 따로 판정합니다."""
    return relevance_tier(title, abstract, keywords) is not None


# ═══════════════════════════════════════════════════════════════════════════
# 4. 학술 검색 엔진 연동 (PubMed, Europe PMC, Crossref, KCI OAI-PMH)
# ═══════════════════════════════════════════════════════════════════════════

def search_europe_pmc(query: str, page_size: int = 10) -> List[dict]:
    """Europe PMC REST API를 이용하여 논문을 검색합니다."""
    encoded_q = urllib.parse.quote(query)

    url = (
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        f"?query={encoded_q}"
        f"&format=json"
        f"&pageSize={page_size}"
        f"&resultType=core"
    )

    response = fetch_with_retry(url)

    if not response:
        return []

    try:
        data = json.loads(response)
        results = data.get("resultList", {}).get("result", [])
    except (json.JSONDecodeError, TypeError):
        return []

    articles = []

    for item in results:
        title = strip_html(item.get("title", ""))
        abstract = strip_html(item.get("abstractText", ""))

        if not is_valid_abstract(abstract):
            continue

        if not is_domain_relevant(title, abstract):
            continue

        doi = item.get("doi", "")
        pmid = item.get("pmid", "")

        articles.append({
            "title": title,
            "abstractText": abstract,
            "authorString": item.get("authorString", "연구진 미상"),
            "journalTitle": item.get("journalTitle", "Academic Journal"),
            "pubYear": item.get("pubYear", ""),
            "doi": doi,
            "pmid": pmid,
            "url": (
                f"https://doi.org/{doi}"
                if doi
                else (
                    f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                    if pmid
                    else ""
                )
            ),
            "_source": "Europe PMC",
            "_lang": "en",
        })

    return articles


def search_pubmed(query: str, page_size: int = 8) -> List[dict]:
    encoded_q = urllib.parse.quote(query)
    esearch_url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        f"?db=pubmed&term={encoded_q}&retmode=json&retmax={page_size}&sort=pub_date"
    )
    esearch_res = fetch_with_retry(esearch_url)
    if not esearch_res:
        return []

    try:
        id_list = json.loads(esearch_res).get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []

        efetch_url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            f"?db=pubmed&id={','.join(id_list)}&retmode=xml"
        )
        efetch_xml = fetch_with_retry(efetch_url)
        if not efetch_xml:
            return []

        root = ET.fromstring(efetch_xml.encode('utf-8'))
        articles = []
        for article_elem in root.findall(".//PubmedArticle"):
            medline = article_elem.find(".//MedlineCitation")
            if medline is None:
                continue
            pmid = medline.findtext(".//PMID", default="")
            art = medline.find(".//Article")
            if art is None:
                continue

            title = strip_html(art.findtext(".//ArticleTitle", default=""))
            parts = []
            for ab in art.findall(".//AbstractText"):
                txt = "".join(ab.itertext()).strip()
                if txt:
                    parts.append(txt)
            abstract = strip_html("\n\n".join(parts))

            if not is_valid_abstract(abstract):
                continue
            if not is_domain_relevant(title, abstract):
                continue

            author_names = []
            for auth in art.findall(".//AuthorList/Author"):
                last = auth.findtext("LastName", "")
                fore = auth.findtext("ForeName", "")
                if last:
                    author_names.append(f"{last} {fore[:1]}".strip() if fore else last)
            author_str = ", ".join(author_names[:4]) + (" et al." if len(author_names) > 4 else "")

            journal = art.findtext(".//Journal/Title") or art.findtext(".//Journal/ISOAbbreviation") or "Academic Journal"
            pub_year = (
                art.findtext(".//JournalIssue/PubDate/Year")
                or medline.findtext(".//DateCompleted/Year")
                or str(datetime.now().year)
            )

            doi = ""
            for id_elem in article_elem.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if id_elem.get("IdType") == "doi":
                    doi = (id_elem.text or "").strip()
                    break

            articles.append({
                "id": pmid,
                "doi": doi,
        "pmid": pmid,
                "title": title,
                "authorString": author_str or "저자 정보 없음",
                "journalTitle": journal,
                "pubYear": pub_year,
                "abstractText": abstract,
                "url": f"https://doi.org/{doi}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "_source": "PubMed",
                "_lang": "en",
            })
        return articles
    except Exception as e:
        print(f"  [!] PubMed 파싱 오류: {e}")
        return []


def search_crossref_korean(query: str, page_size: int = 6, from_date: str = "", issn: str = "") -> List[dict]:
    """Crossref 검색. issn 을 주면 그 저널 안에서만, from_date 를 주면 그 이후 발행분만."""
    filters = ["has-abstract:true"] + ([f"from-pub-date:{from_date}"] if from_date else [])
    base = f"https://api.crossref.org/journals/{issn}/works" if issn else "https://api.crossref.org/works"
    q = f"query={urllib.parse.quote(query)}&" if query else ""
    url = f"{base}?{q}filter={','.join(filters)}&rows={page_size}&sort=published&order=desc"
    resp_text = fetch_with_retry(url)
    if not resp_text:
        return []

    try:
        data = json.loads(resp_text)
        items = data.get("message", {}).get("items", [])
        valid_articles = []

        for item in items:
            raw_title_list = item.get("title", [])
            title = strip_html(raw_title_list[0] if raw_title_list else "")
            abstract = strip_html(item.get("abstract", ""))

            if not is_valid_abstract(abstract):
                continue
            if not is_domain_relevant(title, abstract):
                continue

            authors = []
            for a in item.get("author", []):
                given = a.get("given", "")
                family = a.get("family", "")
                name = f"{family} {given}".strip() or a.get("name", "")
                if name:
                    authors.append(name)
            author_str = ", ".join(authors[:4]) + (" 외" if len(authors) > 4 else "")

            container = item.get("container-title", [])
            journal = container[0] if container else "한국학술지 (Crossref/KCI)"

            pub_year = str(datetime.now().year)
            date_parts = item.get("published", {}).get("date-parts", [[]])[0]
            if date_parts:
                pub_year = str(date_parts[0])

            doi = item.get("DOI", "")
            doi_url = item.get("URL", f"https://doi.org/{doi}" if doi else "#")
            lang = "ko" if any(ord(c) >= 0xAC00 and ord(c) <= 0xD7A3 for c in (title + abstract)) else "en"

            valid_articles.append({
                "id": doi or paper_fingerprint(title),
                "doi": doi,
                "title": title,
                "authorString": author_str or "연구진",
                "journalTitle": journal,
                "pubYear": pub_year,
                "abstractText": abstract,
                "url": doi_url,
                "_source": "Crossref",
                "_lang": lang,
            })

        print(f"  [Crossref] '{query or issn}' -> 유효 논문 {len(valid_articles)}편")
        return valid_articles

    except Exception as e:
        print(f"  [!] Crossref 파싱 오류: {e}")
        return []


KCI_OAI_URL = "https://open.kci.go.kr/oai/request"
_DC = "{http://purl.org/dc/elements/1.1/}"
_OAI = "{http://www.openarchives.org/OAI/2.0/}"


def _has_hangul(text: str) -> bool:
    return any(0xAC00 <= ord(c) <= 0xD7A3 for c in text or "")


def _parse_kci_record(record: ET.Element) -> Optional[dict]:
    """OAI-PMH oai_dc 레코드 1건 → 내부 논문 dict. 삭제 레코드나 메타데이터 없는 건 None."""
    header = record.find(f"{_OAI}header")
    if header is not None and header.get("status") == "deleted":
        return None
    dc = record.find(f"{_OAI}metadata/{{http://www.openarchives.org/OAI/2.0/oai_dc/}}dc")
    if dc is None:
        return None

    def by_lang(tag: str) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for el in dc.findall(f"{_DC}{tag}"):
            if el.text and el.text.strip():
                out.setdefault(el.get("lang", "original"), strip_html(el.text))
        return out

    titles, descs = by_lang("title"), by_lang("description")
    title_ko, title_en = titles.get("original", ""), titles.get("english", "")
    desc_ko, desc_en = descs.get("original", ""), descs.get("english", "")

    # 국문 초록이 충분하면 국문, 아니면 영문 초록을 씁니다.
    abstract = desc_ko if len(desc_ko) >= MIN_ABSTRACT_LENGTH else (desc_en or desc_ko)
    title = title_ko or title_en

    ids = {el.get("type", ""): (el.text or "").strip() for el in dc.findall(f"{_DC}identifier")}
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", ids.get("doi", ""), flags=re.I)
    journal = (ids.get("journalInfo", "").split(",")[0] or dc.findtext(f"{_DC}publisher") or "KCI 등재학술지").strip()
    url = dc.findtext(f"{_DC}url") or (f"https://doi.org/{doi}" if doi else "#")
    date = (dc.findtext(f"{_DC}date") or "").strip()
    creators = (dc.findtext(f"{_DC}creator") or "").split(";")
    # "홍길동(소속)" → "홍길동"
    names = [re.sub(r"\(.*?\)", "", c).strip() for c in creators if c.strip()]

    return {
        "id": ids.get("artiId") or doi or paper_fingerprint(title),
        "doi": doi,
        "title": title,
        "title_en": title_en,
        "abstractText": abstract,
        "abstract_en": desc_en,
        "authorString": ", ".join(names[:4]) + (" 외" if len(names) > 4 else "") if names else "국내 연구진",
        "journalTitle": journal,
        "pubYear": date[:4],
        "subject": dc.findtext(f"{_DC}subject") or "",
        "url": url,
        "_source": "KCI",
        "_lang": "ko" if _has_hangul(title + abstract) else "en",
    }


def _is_domestic(raw: dict) -> bool:
    src = raw.get("_source", raw.get("source", ""))
    return src == "KCI" or "국내" in src or raw.get("_lang", raw.get("lang")) == "ko"


def search_kci_oaipmh(from_date: str, until_date: str, max_pages: int = 400) -> Tuple[List[dict], bool]:
    """
    KCI OAI-PMH 에서 [from_date, until_date] 사이에 '등록·갱신된' 레코드를 전부 받아
    해조류 관련 논문만 남깁니다. (키 불필요)

    - OAI-PMH 는 키워드 검색이 없어서 기간 내 전 분야 레코드를 페이지(100건)씩 받아야 합니다.
      2주치 ≈ 100페이지 · 1만 건 · 약 5~6분.
    - 날짜는 발행일이 아니라 갱신일이라 옛 논문도 섞이므로 발행연도(작년 이후)로 한 번 더 거릅니다.

    반환: (논문 목록, 끝까지 받았는지). 끝까지 못 받았으면 다음 실행 때 같은 시작일부터 다시 받습니다.
    """
    min_year = datetime.now().year - 1
    params: Dict[str, str] = {
        "verb": "ListRecords", "set": "ARTI", "metadataPrefix": "oai_dc",
        "from": from_date, "until": until_date,
    }
    print(f"  [KCI-OAI] {from_date} ~ {until_date} 등록분 하베스팅 (최대 {max_pages}페이지)...")
    articles: List[dict] = []
    seen = 0
    started = time.time()

    for page in range(1, max_pages + 1):
        xml_text = fetch_with_retry(f"{KCI_OAI_URL}?{urllib.parse.urlencode(params)}", timeout=90, max_retries=4)
        if not xml_text:
            print(f"  [!] KCI-OAI {page}페이지 수신 실패 → 이번에는 여기까지만 (다음 실행 때 이어서)")
            return articles, False
        try:
            root = ET.fromstring(xml_text.encode("utf-8"))
        except ET.ParseError as e:
            print(f"  [!] KCI-OAI {page}페이지 XML 오류: {e}")
            return articles, False

        err = root.find(f"{_OAI}error")
        if err is not None:
            if err.get("code") == "noRecordsMatch":
                break
            print(f"  [!] KCI-OAI 오류: {err.get('code')} {err.text}")
            return articles, False

        for rec in root.iter(f"{_OAI}record"):
            seen += 1
            art = _parse_kci_record(rec)
            if not art or not art["pubYear"].isdigit() or int(art["pubYear"]) < min_year:
                continue
            if not is_valid_abstract(art["abstractText"]):
                continue
            if not is_domain_relevant(art["title"] + " " + art["title_en"],
                                      art["abstractText"] + " " + art["abstract_en"], art["subject"]):
                continue
            articles.append(art)

        token = root.find(f".//{_OAI}resumptionToken")
        if page % 20 == 0:
            print(f"    … {page}페이지 / {seen}건 확인 / 관련 {len(articles)}편 ({time.time() - started:.0f}초)")
        if token is None or not (token.text or "").strip():
            print(f"  [KCI-OAI] 완료: {page}페이지 · {seen}건 중 관련 논문 {len(articles)}편 ({time.time() - started:.0f}초)")
            return articles, True
        params = {"verb": "ListRecords", "resumptionToken": token.text.strip()}

    print(f"  [!] KCI-OAI 최대 페이지({max_pages}) 도달 → 나머지는 다음 실행 때 이어서")
    return articles, False


# ═══════════════════════════════════════════════════════════════════════════
# 4-1. 수집 상태 · 기발행 논문 목록 (GitHub Actions 가 함께 커밋)
# ═══════════════════════════════════════════════════════════════════════════

STATE_DIR = BASE_DIR / "data"
PIPELINE_STATE_FILE = STATE_DIR / "pipeline_state.json"
PUBLISHED_FILE = STATE_DIR / "published_papers.json"


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _norm_title(title: str) -> str:
    return re.sub(r"[\W_]+", "", (title or "").lower())


def registry_keys(title: str, doi: str = "") -> List[str]:
    """같은 논문을 DOI 로도, 제목으로도 알아볼 수 있게 키를 2개까지 만듭니다."""
    keys = []
    if doi:
        keys.append("doi:" + doi.strip().lower())
    t = _norm_title(title)
    if len(t) >= 20:
        keys.append("title:" + t[:150])
    return keys


def load_published_registry() -> Dict[str, str]:
    """{키: 실린 호 날짜}. 파일이 없으면 기존 archives/*.md, *.json 에서 처음 한 번 만들어 둡니다."""
    data = _read_json(PUBLISHED_FILE, None)
    if isinstance(data, dict):
        return data
    registry: Dict[str, str] = {}
    for md in sorted(ARCHIVES_DIR.glob("*.md")):
        m_date = re.search(r"\d{4}-\d{2}-\d{2}", md.name)
        issue = m_date.group(0) if m_date else md.stem
        text = md.read_text(encoding="utf-8")
        for block in text.split("\n### ")[1:]:
            m_title = re.search(r"\*\*원문 제목\*\*:\s*([^\n]+)", block)
            m_doi = re.search(r"\[(10\.[^\]]+)\]\(", block)
            if m_title:
                for k in registry_keys(m_title.group(1), m_doi.group(1) if m_doi else ""):
                    registry.setdefault(k, issue)
    print(f"  [기발행 목록] 기존 아카이브에서 {len(registry)}개 키로 초기 생성")
    return registry


def is_already_published(registry: Dict[str, str], title: str, doi: str, today: str) -> bool:
    # 같은 날 다시 실행할 때는 오늘 호에 실린 논문을 다시 허용합니다.
    return any(registry.get(k) not in (None, today) for k in registry_keys(title, doi))


# ═══════════════════════════════════════════════════════════════════════════
# 5. 안전한 카테고리 매칭
# ═══════════════════════════════════════════════════════════════════════════

CATEGORY_ORDER = [
    "breeding_molecular_pathology",
    "thallus_lifecycle_conchocelis",
    "smart_aquaculture_mass_culture",
    "blue_carbon_feed_methane"
]

RELATED_CATEGORY = "related_research"

CATEGORY_NAME_MAP = {
    "breeding_molecular_pathology": ("01", "육종 · 분자생물학 · 병해", "Breeding & Pathology", "rose"),
    "thallus_lifecycle_conchocelis": ("02", "엽체 생리 · 생활사 · 사상체", "Thallus & Life Cycle", "emerald"),
    "smart_aquaculture_mass_culture": ("03", "스마트 양식 및 대량 배양 기술", "Smart Aquaculture & Mass Culture", "violet"),
    "blue_carbon_feed_methane": ("04", "블루카본 및 산업적 응용", "Blue Carbon & Applications", "cyan"),
    RELATED_CATEGORY: ("05", "연관 연구", "Related Research", "amber"),
}
# 마크다운 섹션 출력 순서 (분류 점수 계산은 CATEGORY_ORDER 4개만 사용)
SECTION_ORDER = CATEGORY_ORDER + [RELATED_CATEGORY]

def classify_article_safe(article: dict, taxa_list: list, categories_raw: Any) -> Tuple[List[str], str]:
    title = article.get("title", "")
    abstract = article.get("abstractText", "")
    full_text = f"{title} {abstract}".lower()

    matched_taxa: List[str] = []
    if isinstance(taxa_list, list):
        for taxa in taxa_list:
            if not isinstance(taxa, dict) or not taxa.get("enabled", True):
                continue
            candidates = [taxa.get("name", "")] + taxa.get("aliases", []) + taxa.get("korean_names", [])
            for cand in candidates:
                if cand and cand.lower() in full_text:
                    matched_taxa.append(taxa["name"])
                    break

    cat_scores: Dict[str, int] = {cid: 0 for cid in CATEGORY_ORDER}

    if isinstance(categories_raw, dict):
        for cid, cinfo in categories_raw.items():
            if cid not in cat_scores:
                cat_scores[cid] = 0
            if isinstance(cinfo, dict):
                kws = cinfo.get("keywords", [])
                if isinstance(kws, list):
                    for kw in kws:
                        if isinstance(kw, str) and kw.lower() in full_text:
                            cat_scores[cid] += 1
                kws_ko = cinfo.get("keywords_ko", [])
                if isinstance(kws_ko, list):
                    for kw in kws_ko:
                        if isinstance(kw, str) and kw.lower() in full_text:
                            cat_scores[cid] += 3
            elif isinstance(cinfo, list):
                for kw in cinfo:
                    if isinstance(kw, str) and kw.lower() in full_text:
                        cat_scores[cid] += 1
            elif isinstance(cinfo, str):
                if cinfo.lower() in full_text:
                    cat_scores[cid] += 2

    if any(k in full_text for k in ["dna", "barcode", "genom", "crispr", "유전체", "전사체", "품종", "병해", "pathogen", "pcr"]):
        cat_scores["breeding_molecular_pathology"] += 3
    if any(k in full_text for k in ["conchocel", "spore", "thallus", "광합성", "각포자", "사상체", "엽체", "pigment", "생리"]):
        cat_scores["thallus_lifecycle_conchocelis"] += 3
    if any(k in full_text for k in ["bioreactor", "aquaculture", "seeding", "배양", "채묘", "양식", "smart", "반응기"]):
        cat_scores["smart_aquaculture_mass_culture"] += 3
    if any(k in full_text for k in ["carbon", "methane", "rdoc", "asparagopsis", "블루카본", "메탄", "사료", "탄소격리"]):
        cat_scores["blue_carbon_feed_methane"] += 3

    best_cat = max(cat_scores.items(), key=lambda x: x[1])[0]
    if cat_scores[best_cat] == 0:
        best_cat = "thallus_lifecycle_conchocelis"

    return list(set(matched_taxa)), best_cat


# ═══════════════════════════════════════════════════════════════════════════
# 6. 썸네일 → common.assign_unique_thumbnails (호 단위로 중복 없이 배정)
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
# 7. 동적 요약 엔진 (Gemini ➔ Claude ➔ 룰베이스 하이브리드)
# ═══════════════════════════════════════════════════════════════════════════

SUMMARY_PROMPT_VERSION = "v4"  # 프롬프트를 바꾸면 올려서 캐시를 무효화하세요.


def _parse_ai_json(text: str) -> Optional[dict]:
    """AI 응답에서 JSON 객체를 꺼냅니다 (```json 코드펜스가 섞여도 처리)."""
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


# Gemini 모델 순서: GEMINI_MODEL (쉼표로 여러 개 가능) → 기본값.
# "gemini-flash-latest" 같은 별칭은 Google이 가리키는 모델을 바꾸므로 버전을 고정합니다.
DEFAULT_GEMINI_MODELS = "gemini-flash-lite-latest,gemini-3.6-flash"
DEFAULT_CLAUDE_MODEL = "claude-haiku-5-5"

# 이번 실행에서 계속 실패한 모델은 건너뜁니다 (논문마다 같은 대기 시간을 반복하지 않도록).
_UNAVAILABLE_MODELS: Set[str] = set()


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=get_ssl_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _call_gemini(prompt: str) -> Optional[dict]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    models = [m.strip() for m in (os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODELS).split(",") if m.strip()]
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}  # 키는 URL 이 아닌 헤더로
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }

    for model in models:
        if model in _UNAVAILABLE_MODELS:
            continue
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(3):
            try:
                res = _post_json(url, payload, headers, timeout=60)
                cands = res.get("candidates") or []
                if not cands:
                    print(f"  [-] Gemini({model}) 빈 응답 (promptFeedback={res.get('promptFeedback')})")
                    break
                parts = cands[0].get("content", {}).get("parts") or [{}]
                return _parse_ai_json(parts[0].get("text", ""))
            except urllib.error.HTTPError as he:
                body = he.read().decode("utf-8", "replace")[:300]
                if he.code in (400, 401, 403):
                    raise RuntimeError(f"Gemini 키/요청 오류 HTTP {he.code}: {body}")
                if he.code == 404:
                    print(f"  [-] Gemini 모델 '{model}' 사용 불가(404) → 다음 모델")
                    _UNAVAILABLE_MODELS.add(model)
                    break
                if he.code == 429 and "per day" in body.lower():
                    print(f"  [-] Gemini({model}) 일일 한도 소진 → 다음 모델")
                    _UNAVAILABLE_MODELS.add(model)
                    break
                reason = f"HTTP {he.code}"
            except (TimeoutError, urllib.error.URLError) as e:
                reason = f"응답 지연({e})"
            if attempt < 2:
                wait = 5 * (2 ** attempt)  # 5 → 10초
                print(f"  [재시도] Gemini({model}) {reason} → {wait}초 후 재시도")
                time.sleep(wait)
            else:
                print(f"  [-] Gemini({model}) 3회 실패 → 이번 실행에서는 다음 모델 사용")
                _UNAVAILABLE_MODELS.add(model)
    return None


def _call_claude(prompt: str) -> Optional[dict]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.environ.get("CLAUDE_MODEL") or DEFAULT_CLAUDE_MODEL
    if model in _UNAVAILABLE_MODELS:
        return None
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {"model": model, "max_tokens": 1200, "messages": [{"role": "user", "content": prompt}]}
    for attempt in range(2):
        try:
            res = _post_json("https://api.anthropic.com/v1/messages", payload, headers, timeout=90)
            text = "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")
            return _parse_ai_json(text)
        except urllib.error.HTTPError as he:
            if he.code in (429, 500, 529) and attempt == 0:
                print(f"  [재시도] Claude HTTP {he.code} → 10초 후 재시도")
                time.sleep(10)
                continue
            body = he.read().decode("utf-8", "replace")[:300]
            if he.code in (400, 401, 403, 404):
                # 크레딧 부족·키 오류·모델 없음은 재시도해도 같으므로 이번 실행에서는 Claude 를 끕니다.
                _UNAVAILABLE_MODELS.add(model)
            raise RuntimeError(f"Claude HTTP {he.code}: {body}")
    return None


def _ai_callers() -> List[Tuple[str, Any]]:
    """AI_PROVIDER=claude 면 Claude 먼저, 그 외(기본)는 Gemini 먼저."""
    order = [("gemini", _call_gemini), ("claude", _call_claude)]
    if os.environ.get("AI_PROVIDER", "gemini").strip().lower() == "claude":
        order.reverse()
    return order


def generate_natural_summary(
    title: str,
    abstract: str,
    category_name: str,
    taxa_list: List[str],
    paper_lang: str = "en",
    doi: str = ""
) -> Dict[str, Any]:
    cache = load_summary_cache()
    cache_key = f"{SUMMARY_PROMPT_VERSION}:{paper_fingerprint(title, doi)}"
    if cache_key in cache:
        cached = dict(cache[cache_key])
        cached["takeaways"], cached["implications"] = clean_summary(
            cached.get("takeaways", []), cached.get("implications", ""), abstract
        )
        cached["is_cached"] = True
        return cached

    taxa_str = ", ".join(taxa_list) if taxa_list else category_name
    lang_prompt = (
        "한국어(국문)로 작성된 국내 논문입니다. 모든 분석 출력을 세련된 국문으로 작성하세요."
        if paper_lang == "ko" else
        "영문(English) 국제 논문입니다. 분석 결과는 자연스러운 한국어로 번역/요약하여 작성하세요."
    )
    prompt = f"""당신은 해조류 및 해양 블루카본 분야의 수석 연구위원이자 학술 매거진 편집장입니다.
{lang_prompt}
아래 실제 논문 초록만을 바탕으로 매거진 카드 데이터를 JSON으로 작성하세요.

★ 금지 및 필수 지침:
1. '연구 목적:', '주요 성과:', '결론:' 같은 템플릿 접두사를 쓰지 마세요.
2. 초록에 있는 실제 수치(%, 농도, 유전자, 일수 등)와 구체적 발견을 근거로 쓰세요. 초록에 없는 내용은 지어내지 마세요.
3. takeaways 3개는 서로 다른 내용(배경 / 핵심 결과 / 결론)이어야 하며, 초록 문장을 그대로 옮기지 말고 요약하세요.
4. implications 는 takeaways 의 어느 문장과도 겹치지 않는, 현장 양식가·연구자·정책 담당자 관점의 "그래서 무엇을 할 수 있나"를 쓰세요.
   '본 연구는 ~에 기여합니다' 같은 상투적 문장은 금지입니다.

[논문 정보]
- 논문 제목: {title}
- 대상 생물군: {taxa_str}
- 연구 분야: {category_name}
- 실제 초록:
{abstract[:3000]}

[출력 형식 - 순수 JSON만 반환]
{{
  "headline": "논문 핵심을 압축한 35~55자 안팎의 국문 헤드라인",
  "takeaways": ["연구 배경·목적 (1문장)", "핵심 실험 결과와 수치 (1문장)", "연구진의 결론 (1문장)"],
  "implications": "takeaways 와 겹치지 않는 실질적 시사점 (1~2문장)"
}}"""

    if len(abstract) >= 200:
        for source, caller in _ai_callers():
            try:
                parsed = caller(prompt)
            except Exception as e:
                print(f"  [-] {source} 요약 실패 (논문: {title[:30]}…): {e}")
                continue
            if not parsed:
                continue
            takeaways, implications = clean_summary(
                parsed.get("takeaways", []), parsed.get("implications", ""), abstract
            )
            if len(takeaways) < 2:
                print(f"  [-] {source} 응답 품질 미달(takeaway {len(takeaways)}개) → 다음 단계로")
                continue
            result = {
                "headline": (parsed.get("headline") or title).strip(),
                "takeaways": takeaways,
                "implications": implications,
                "is_ai": True,
                "summary_source": source,
            }
            cache[cache_key] = result
            save_summary_cache(cache)
            return result

    # ── AI 를 못 쓰면 초록에서 추출 (캐시하지 않음 → 다음 실행 때 AI 재시도) ──
    headline = title
    if len(title) > 65:
        tokens = title[:65].rsplit(" ", 1)
        headline = (tokens[0] if len(tokens) > 1 else title[:65]) + "…"
    takeaways, implications = extractive_summary(abstract)
    return {
        "headline": headline,
        "takeaways": takeaways or [title],
        "implications": implications,
        "is_ai": False,
        "summary_source": "abstract_extract",
    }


# ═══════════════════════════════════════════════════════════════════════════
# 8. 메인 파이프라인
# ═══════════════════════════════════════════════════════════════════════════

def run_pipeline() -> None:
    print("=" * 70)
    print("🌊 Phyco & Blue Carbon Research Magazine Pipeline (v3.0 Production)")
    print(f"   실행 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("   수집 원칙: 깡통 논문(초록 < 200자) 원천 배제 · 해조류 전문 도메인 엄격 검증")
    print("   데이터 소스: PubMed · Europe PMC · Crossref · KCI OAI-PMH")
    print("=" * 70)

    config = load_keywords()
    target_taxa = config.get("target_taxa", {}).get("genera", [])
    categories_raw = config.get("research_categories", {})
    settings = config.get("search_settings", {})
    # 기발행 논문을 빼므로 기간을 넉넉히 잡아도 같은 논문이 반복되지 않습니다.
    intl_days = int(settings.get("days_lookback_international", 60))
    domestic_days = int(settings.get("days_lookback_domestic", 365))
    kci_initial_days = int(settings.get("kci_initial_days", 14))
    kci_max_pages = int(settings.get("kci_max_pages", 400))
    max_papers = int(settings.get("max_papers_per_issue", 60))
    max_related = int(settings.get("max_related_per_issue", 10))

    today = datetime.now().date()
    today_str = today.isoformat()
    published = load_published_registry()
    state = _read_json(PIPELINE_STATE_FILE, {})
    skipped_published = 0

    collected: Dict[str, dict] = {}

    def _add_article(item: dict) -> None:
        nonlocal skipped_published
        title = item.get("title", "")
        doi = item.get("doi", "")
        abstract = item.get("abstractText", "")

        if not is_valid_abstract(abstract):
            return
        # KCI 는 국문·영문 제목/초록이 따로 있어 둘 다 봅니다.
        tier = relevance_tier(f"{title} {item.get('title_en', '')}", f"{abstract} {item.get('abstract_en', '')}")
        if tier is None:
            return
        if is_already_published(published, title, doi, today_str):
            skipped_published += 1
            return

        pmid = item.get("pmid", item.get("id", ""))
        fp = paper_fingerprint(title, doi, pmid)
        if fp not in collected:
            item["_tier"] = tier
            collected[fp] = item

    # ──────────────────────────────────────────────────────────────────
    # STEP 1: 글로벌 영문 DB 수집 (PubMed & Europe PMC)
    # ──────────────────────────────────────────────────────────────────
    date_from = (today - timedelta(days=intl_days)).isoformat()
    date_to = today_str
    print(f"\n[1/5] 글로벌 영문 DB 검색 중 (PubMed & Europe PMC, {date_from} 이후)...")

    for taxa in target_taxa:
        if not isinstance(taxa, dict) or not taxa.get("enabled", True):
            continue
        taxa_name = taxa.get("name", "")
        print(f"  → 영문 생물군 '{taxa_name}' 검색...")

        epmc_q = f'("{taxa_name}") AND (FIRST_PDATE:[{date_from} TO {date_to}])'
        epmc_items = search_europe_pmc(epmc_q, page_size=25)
        if len(epmc_items) < 2:
            aliases = taxa.get("aliases") or [taxa_name]
            alias_terms = " OR ".join(f'"{a}"' for a in aliases[:3])
            epmc_q = f'({alias_terms}) AND (FIRST_PDATE:[{date_from} TO {date_to}])'
            epmc_items += search_europe_pmc(epmc_q, page_size=25)
        for it in epmc_items:
            _add_article(it)

        pubmed_q = (
            f'{taxa_name}[Title/Abstract] AND '
            f'("{date_from}"[Date - Publication] : "{date_to}"[Date - Publication])'
        )
        for it in search_pubmed(pubmed_q, page_size=20):
            _add_article(it)

    # ──────────────────────────────────────────────────────────────────
    # STEP 2: 국내 논문 (KCI OAI-PMH 증분 수집 + Crossref)
    # ──────────────────────────────────────────────────────────────────
    print("\n[2/5] 국내 학술지 논문 검색 중 (KCI OAI-PMH & Crossref)...")

    # KCI: 지난번에 받은 날짜 이후분만 (처음이면 최근 kci_initial_days 일)
    kci_from = state.get("kci_oai_harvested_until") or (today - timedelta(days=kci_initial_days)).isoformat()
    kci_items, kci_complete = search_kci_oaipmh(kci_from, today_str, max_pages=kci_max_pages)
    for it in kci_items:
        _add_article(it)

    domestic_from = (today - timedelta(days=domestic_days)).isoformat()
    korean_queries = [
        "김 양식", "해조류 육종", "사상체 각포자", "블루카본 해조류",
        "방사무늬김", "잇바디돌김", "바다고리풀 메탄", "해조류 바이오리액터"
    ]
    for kq in korean_queries:
        for it in search_crossref_korean(kq, page_size=10, from_date=domestic_from):
            _add_article(it)
    # 초록을 Crossref 에 꾸준히 등록하는 국내 해조류 저널
    for issn in settings.get("crossref_domestic_issns", ["1226-2617"]):  # Algae (한국조류학회)
        for it in search_crossref_korean("", page_size=40, from_date=domestic_from, issn=issn):
            it["_source"] = "Crossref (국내 저널)"
            _add_article(it)

    print(f"\n  기발행 논문 제외: {skipped_published}편")
    # 상한: 핵심 논문은 max_papers_per_issue, 연관 연구는 max_related_per_issue. 국내 논문을 먼저 남깁니다.
    def _cap(items: List[Tuple[str, dict]], limit: int, label: str) -> List[Tuple[str, dict]]:
        items = sorted(items, key=lambda kv: not _is_domestic(kv[1]))
        if len(items) > limit:
            print(f"  [!] {label} {len(items)}편 > 상한 {limit}편 → 초과분은 다음 호로")
        return items[:limit]

    core_items = [kv for kv in collected.items() if kv[1].get("_tier") == "core"]
    related_items = [kv for kv in collected.items() if kv[1].get("_tier") == "related"]
    print(f"  핵심 논문 {len(core_items)}편 · 연관 연구 {len(related_items)}편")
    collected = dict(_cap(core_items, max_papers, "핵심 논문") + _cap(related_items, max_related, "연관 연구"))

    # ──────────────────────────────────────────────────────────────────
    # STEP 3: 논문 분류 및 동적 요약 생성 (캐시 시스템 연동)
    # ──────────────────────────────────────────────────────────────────
    print(f"\n[3/5] 수집된 {len(collected)}편 실존 논문 분류 및 초록 기반 요약 생성...")
    processed_papers: List[dict] = []

    for idx, (fp, raw) in enumerate(collected.items(), 1):

        title = raw.get("title", "").rstrip(".")
        abstract = raw.get("abstractText", "")
        author_str = raw.get("authorString", "연구진 미상")
        journal = raw.get("journalTitle") or "Academic Journal"
        pub_year = str(raw.get("pubYear", datetime.now().year))
        source = raw.get("_source", "Database")
        paper_lang = raw.get("_lang", "en")
        doi = raw.get("doi", "")
        doi_url = raw.get("url") or (f"https://doi.org/{doi}" if doi else "#")

        matched_taxa, best_cat = classify_article_safe(raw, target_taxa, categories_raw)
        tier = raw.get("_tier", "core")
        if tier == "related":
            best_cat = RELATED_CATEGORY
        if not matched_taxa:
            matched_taxa = ["Unclassified"]

        meta = CATEGORY_NAME_MAP.get(best_cat, ("02", "엽체 생리 · 생활사 · 사상체", "Thallus", "emerald"))
        cat_no, cat_name_ko, cat_name_en, badge_color = meta

        summary = generate_natural_summary(
            title=title,
            abstract=abstract,
            category_name=cat_name_ko,
            taxa_list=matched_taxa,
            paper_lang=paper_lang,
            doi=doi
        )

        paper = {
            "title": title,
            "headline": summary["headline"],
            "takeaways": summary["takeaways"],
            "implications": summary["implications"],
            "thumbnail_url": "",  # STEP 3 끝에서 호 전체를 보고 중복 없이 배정
            "abstract": abstract,
            "authors": author_str,
            "journal": journal,
            "year": pub_year,
            "doi": doi,
            "url": doi_url,
            "taxa": matched_taxa,
            "category": best_cat,
            "category_name": cat_name_ko,
            "badge_color": badge_color,
            "source": source,
            "lang": paper_lang,
            "tier": tier,
            "is_domestic": _is_domestic(raw),
            "is_ai_summary": summary.get("is_ai", False),
            "summary_source": summary.get("summary_source", "unknown"),
        }
        processed_papers.append(paper)
        if summary.get("is_ai") and not summary.get("is_cached"):
            time.sleep(4.5)  # AI 호출한 경우만 대기 (Gemini 무료 티어 분당 한도)
        src_tag = f"[{source}]"
        cache_status = "✨[캐시]" if summary.get("is_cached") else ""
        print(f"  [{idx:02d}] {src_tag} {cache_status} {title[:45]}…")

    if not processed_papers:
        print("[!] 이번 실행에서 확정된 논문이 0편입니다. 기존 아카이브/JSON 을 덮어쓰지 않고 종료합니다.")
        return

    assign_unique_thumbnails(processed_papers)

    # ──────────────────────────────────────────────────────────────────
    # STEP 4: 영구 마크다운 아카이브 생성 및 저장
    # ──────────────────────────────────────────────────────────────────
    print("\n[4/5] 4분할 섹션 영구 마크다운 아카이브 빌드 중...")
    archive_file = ARCHIVES_DIR / f"{today_str}-weekly-digest.md"

    cat_grouped: Dict[str, List[dict]] = {cid: [] for cid in SECTION_ORDER}
    for p in processed_papers:
        cat_grouped.setdefault(p["category"], []).append(p)

    taxa_all_set = list({t for p in processed_papers for t in p["taxa"]})
    sources_used = list({p["source"] for p in processed_papers})

    frontmatter = (
        f'---\n'
        f'title: "김·바다고리풀속 및 블루카본 연구 격주 다이제스트 ({today_str})"\n'
        f'date: "{today_str}"\n'
        f'version: "3.0"\n'
        f'total_papers: {len(processed_papers)}\n'
        f'sources: {json.dumps(sources_used, ensure_ascii=False)}\n'
        f'taxa_covered: {json.dumps(taxa_all_set, ensure_ascii=False)}\n'
        f'categories: {json.dumps(list(cat_grouped.keys()), ensure_ascii=False)}\n'
        f'tags: ["Phyco", "BlueCarbon", "Seaweed", "Crossref", "KCI", "PubMed"]\n'
        f'---\n'
    )

    md_body = [
        frontmatter,
        f"# 🌊 김/바다고리풀속 및 블루카본 연구 격주 매거진 ({today_str})\n",
        f"> **발행일**: {today_str} | **총 수록 논문**: {len(processed_papers)}편 (초록 검증 완료) | **수집 소스**: {', '.join(sources_used)}  ",
        f"> **대상 생물군**: {', '.join(taxa_all_set) or 'Pyropia, Asparagopsis'}\n",
        "---\n",
    ]

    for cat_id in SECTION_ORDER:
        meta = CATEGORY_NAME_MAP[cat_id]
        cat_no, cat_name_ko, cat_name_en, _ = meta
        papers_in_cat = cat_grouped.get(cat_id, [])
        if not papers_in_cat:
            continue

        md_body.append(f"## 🔬 SECTION {cat_no}: {cat_name_ko} ({cat_name_en})\n")
        md_body.append(f"> 💡 **Research Briefing**: 본 섹션에서는 {cat_name_ko} 분야의 최신 연구 성과 {len(papers_in_cat)}편을 엄선하여 브리핑합니다.\n")

        for pidx, paper in enumerate(papers_in_cat, 1):
            lang_tag = "🇰🇷 국내" if paper.get("is_domestic") else "🌐 해외"
            md_body.append(f"### {pidx}. {paper['headline']}")
            md_body.append(f"- **원문 제목**: {paper['title']}")
            md_body.append(f"- **저자**: {paper['authors']}")
            md_body.append(f"- **저널**: *{paper['journal']}* ({paper['year']}) | **출처**: {lang_tag} {paper['source']} | **원문 열람**: [{paper['doi'] or 'Link'}]({paper['url']})")
            md_body.append(f"- **대상 생물군**: `{', '.join(paper['taxa'])}`")
            md_body.append(f"- **대표 이미지**: ![]({paper['thumbnail_url']})\n")

            md_body.append("#### 📌 핵심 요약 포인트 (Key Takeaways)")
            for t_idx, t_point in enumerate(paper["takeaways"], 1):
                md_body.append(f"{t_idx}. {t_point}")
            md_body.append("")

            if paper.get("implications"):
                md_body.append(f"#### 💡 연구자 시사점 (Researcher's Takeaway)\n{paper['implications']}\n")

            md_body.append(f"#### 📄 논문 초록 전문 (Abstract)\n{paper['abstract']}\n")
            md_body.append("---\n")

    if processed_papers:
        md_body.append("## 📊 이번 호 수록 논문 메타데이터 한눈에 보기\n")
        md_body.append("| 헤드라인 | 생물군 | 섹션 | 소스 | 원문 링크 |")
        md_body.append("|:---|:---|:---|:---:|:---:|")
        for p in processed_papers[:35]:
            hl = (p['headline'][:48] + "…") if len(p['headline']) > 48 else p['headline']
            src_icon = "🇰🇷" if p.get("is_domestic") else "🌐"
            md_body.append(f"| {hl} | *{', '.join(p['taxa'])}* | {p['category_name']} | {src_icon} {p['source']} | [열람]({p['url']}) |")
        md_body.append("\n---\n*Phyco & Blue Carbon Research Archive Pipeline v3.0*")

    with open(archive_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md_body))
    print(f"  => Markdown 아카이브 영구 저장 완료: {archive_file}")

    # ──────────────────────────────────────────────────────────────────
    # STEP 5: 프론트엔드 최신 JSON 데이터 갱신
    # ──────────────────────────────────────────────────────────────────
    latest_data = {
        "date": today_str,
        "version": "3.0",
        "total_papers": len(processed_papers),
        "sources_used": sources_used,
        "taxa": taxa_all_set,
        "articles": processed_papers,
    }
    # build_site.py 는 이 JSON 을 우선 읽습니다 (마크다운 재파싱으로 요약이 깨지는 문제 방지).
    with open(archive_file.with_suffix(".json"), "w", encoding="utf-8") as f:
        json.dump(latest_data, f, ensure_ascii=False, indent=2)

    json_path = PUBLIC_DATA_DIR / "latest-articles.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(latest_data, f, ensure_ascii=False, indent=2)
    print(f"  => 프론트엔드 JSON 데이터 갱신 완료: {json_path}")

    for p in processed_papers:
        for k in registry_keys(p["title"], p.get("doi", "")):
            published[k] = today_str
    _write_json(PUBLISHED_FILE, published)
    if kci_complete:
        state["kci_oai_harvested_until"] = today_str
    state["last_run"] = today_str
    _write_json(PIPELINE_STATE_FILE, state)
    print(f"  => 기발행 목록 {len(published)}개 키 · KCI 수집 기준일 {state.get('kci_oai_harvested_until', '-')}")

    ko_count = sum(1 for p in processed_papers if p.get("is_domestic"))
    en_count = len(processed_papers) - ko_count
    print(f"\n[5/5] 파이프라인 완수! 총 {len(processed_papers)}편 실존 논문 확정 (국내: {ko_count}편 / 해외: {en_count}편)")
    print("=" * 70)


if __name__ == "__main__":
    run_pipeline()
