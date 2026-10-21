# -*- coding: utf-8 -*-
"""
fetch_and_archive.py 와 build_site.py 가 함께 쓰는 공통 로직.

- 썸네일: 한 호(issue) 안에서 같은 사진이 두 번 나오지 않도록 배정
- 요약 정리: 템플릿 접두사 제거, takeaway/시사점 중복 제거, 초록 기반 추출 요약
"""

import difflib
import hashlib
import html
import re
from typing import Dict, Iterable, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════
# 썸네일
# ═══════════════════════════════════════════════════════════════════════════

# Unsplash 사진 ID. 각 사진은 한 카테고리에만 속합니다 (카테고리 간 중복 없음).
# 2026-10-21 기준 모두 HTTP 200 확인. 404 였던 8개는 제거했습니다.
CATEGORY_IMAGE_IDS: Dict[str, List[str]] = {
    "breeding_molecular_pathology": [
        "1532187863486-abf9dbad1b69", "1579154204601-01588f351e67", "1618005182384-a83a8bd57fbe",
        "1507668077129-56e32842fceb", "1484557052118-f32bd25b45b5", "1530497610245-94d3c16cda28",
        "1582719471384-894fbb16e074", "1576086213369-97a306d36557", "1581093588401-fbb62a02f120",
        "1514933651103-005eec06c04b", "1582719508461-905c673771fd", "1581093450021-4a7360e9a6b5",
        "1532094349884-543bc11b234d", "1576086476234-1103be98f096",
    ],
    "thallus_lifecycle_conchocelis": [
        "1544551763-46a013bb70d5", "1518837695005-2083093ee35b", "1507525428034-b723cf961d3e",
        "1559827260-dc66d52bef19", "1516026672322-bc52d61a55d5", "1682687220063-4742bd7fd538",
        "1508672019048-805c876b67e2", "1528183429752-a97d0bf99b5a", "1498084393753-b411b2d26b34",
        "1506744038136-46273834b3fb", "1469854523086-cc02fe5d8800", "1473448912268-2022ce9509d8",
    ],
    "smart_aquaculture_mass_culture": [
        "1565193566173-7a0ee3dbe261", "1594122230689-45899d9e6f69", "1530541930197-ff16ac917b0e",
        "1574943320219-553eb213f72d", "1524492412937-b28074a5d7da", "1581092160607-ee22621dd758",
        "1581092580497-e0d23cbdf1dc", "1504384308090-c894fdcc538d", "1581092795360-fd1ca04f0952",
    ],
    "blue_carbon_feed_methane": [
        "1682687220199-d0124f48f95b", "1500595046743-cd271d694d30", "1552728089-57bdde30beb3",
        "1473341304170-971dccb5ac1e", "1534951009808-766178b47a4f", "1464822759023-fed622ff2c3b",
        "1516214104703-d870798883c5", "1509316975850-ff9c5deb0cd9", "1513836279014-a89f7a76ae86",
        "1518241353330-0f7941c2d9b5", "1451187580459-43490279c0fa", "1542601906990-b4d3fb778b09",
        "1500382017468-9049fed747ef",
    ],
}
LEGACY_CATEGORY_MAP = {"thallus_lifecycle_cultivation": "thallus_lifecycle_conchocelis"}
DEFAULT_CATEGORY = "thallus_lifecycle_conchocelis"

_ALL_IDS = {pid for ids in CATEGORY_IMAGE_IDS.values() for pid in ids}
_PHOTO_ID_RE = re.compile(r"photo-([0-9a-f]+-[0-9a-f]+)")


def image_url(photo_id: str) -> str:
    return f"https://images.unsplash.com/photo-{photo_id}?auto=format&fit=crop&w=800&q=80"


def photo_id_of(url: str) -> Optional[str]:
    """URL 에서 Unsplash 사진 ID 를 꺼냅니다. (?sig= 같은 쿼리는 무시 → 실제 같은 사진인지 판단)"""
    m = _PHOTO_ID_RE.search(url or "")
    return m.group(1) if m else None


def _stable_hash(*parts: str) -> int:
    return int(hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:8], 16)


def assign_unique_thumbnails(papers: List[dict]) -> None:
    """
    한 호의 논문 목록에 썸네일을 배정합니다 (in-place, `thumbnail_url` 키).

    1) 이미 가진 썸네일이 살아있는 사진이고 아직 안 쓰였으면 유지
    2) 아니면 자기 카테고리 풀에서 논문 해시 위치부터 안 쓴 사진
    3) 카테고리 풀이 다 찼으면 다른 카테고리 풀에서 안 쓴 사진
    4) 전체 풀(48장)보다 논문이 많을 때만 어쩔 수 없이 재사용
    """
    used: set = set()
    pending: List[dict] = []

    for p in papers:
        pid = photo_id_of(p.get("thumbnail_url", ""))
        if pid in _ALL_IDS and pid not in used:
            used.add(pid)
            p["thumbnail_url"] = image_url(pid)
        else:
            pending.append(p)

    for p in pending:
        cat = LEGACY_CATEGORY_MAP.get(p.get("category", ""), p.get("category", ""))
        own = CATEGORY_IMAGE_IDS.get(cat, CATEGORY_IMAGE_IDS[DEFAULT_CATEGORY])
        others = [pid for c, ids in CATEGORY_IMAGE_IDS.items() if c != cat for pid in ids]
        start = _stable_hash(p.get("title", ""), p.get("doi", "")) % len(own)
        rotated = own[start:] + own[:start]

        chosen = next((pid for pid in rotated + others if pid not in used), None)
        if chosen is None:
            chosen = rotated[0]
            print(f"  [!] 썸네일 풀({len(_ALL_IDS)}장)보다 논문이 많아 재사용: {p.get('title', '')[:40]}")
        used.add(chosen)
        p["thumbnail_url"] = image_url(chosen)


# ═══════════════════════════════════════════════════════════════════════════
# 문장 분리 / 요약 정리
# ═══════════════════════════════════════════════════════════════════════════

def strip_html(text: str) -> str:
    if not text:
        return ""
    # Europe PMC 는 제목에 "&lt;i&gt;Pyropia&lt;/i&gt;" 처럼 이스케이프된 태그를 줍니다 → 먼저 풀고 태그 제거
    cleaned = re.sub(r"<[^>]+>", " ", html.unescape(text))
    cleaned = re.sub(r"\s+([,.;:)])", r"\1", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def split_into_sentences(text: str) -> List[str]:
    if not text:
        return []
    cleaned = strip_html(text)
    cleaned = re.sub(r"\[[가-힣A-Za-z0-9\s/_-]+\]", "", cleaned)
    # "BACKGROUND:", "RESULTS:" 같은 구조화 초록 라벨 제거 (문장 중간에 있어도)
    cleaned = re.sub(r"\b(?:BACKGROUND|OBJECTIVES?|METHODS?|RESULTS?|CONCLUSIONS?|AIMS?|PURPOSE)\s*:\s*", "", cleaned)

    # 소수점(3.5)·약어(e.g., et al., sp.) 에서 잘리지 않도록: 마침표 뒤 공백 + 대문자/한글로 시작할 때만 분리
    pattern = (
        r"(?<!\bet al\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bsp\.)(?<!\bvs\.)(?<!\bcf\.)"
        r"(?<=[.!?])\s+(?=[가-힣A-Z(])"
        r"|(?<=[다요음함임됨]\.)\s*"
    )
    raw = [s.strip() for s in re.split(pattern, cleaned) if s and s.strip()]

    out: List[str] = []
    for s in raw:
        s = re.sub(r"\s+", " ", s).strip()
        if len(s) < 15:
            continue
        if not s.endswith((".", "!", "?")):
            s += "."
        out.append(s)
    return out


TEMPLATE_PREFIX_RE = re.compile(
    r"^\s*(?:연구\s*목적|연구\s*배경|주요\s*발견|주요\s*성과|결론\s*및\s*성과|결론|시사점|실험\s*분석)\s*[:：]\s*"
)
# 예전 파이프라인이 모든 논문에 붙이던 범용 시사점 ("본 연구는 Pyropia의 ... 가이드라인을 제공합니다." 등)
GENERIC_IMPLICATION_RE = re.compile(r"^본 연구는 .{0,160}(?:제공합니다|기여합니다|제시합니다)\.?$")


def _norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", (s or "").lower())


def is_near_duplicate(a: str, b: str, threshold: float = 0.82) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(shorter) >= 30 and shorter in longer:
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= threshold


def _dedupe(items: Iterable[str], against: Iterable[str] = ()) -> List[str]:
    kept: List[str] = []
    against = list(against)
    for it in items:
        if not it:
            continue
        if any(is_near_duplicate(it, k) for k in kept + against):
            continue
        kept.append(it)
    return kept


IMPLICATION_SIGNAL_RE = re.compile(
    r"시사|기여|기대|제시|전망|응용|활용|향후|의의|가능성|전략|"
    r"suggest|impl(?:y|ies|ication)|conclu|highlight|potential|could|may be|promising|"
    r"provide[sd]? (?:a |new |insight|evidence|basis)|application|insight|useful",
    re.I,
)
DATA_SIGNAL_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|°C|μ|mg|g|kg|L|mL|ppm|fold|배|일|days?)|발현|유의|증가|감소|"
    r"significant|increase|decrease|reduc|enhanc|found|showed|revealed|identified",
    re.I,
)


def extractive_summary(abstract: str) -> Tuple[List[str], str]:
    """
    AI 없이 초록에서 (takeaways 최대 3개, implications) 를 뽑습니다.
    시사점을 먼저 고르고, takeaway 는 남은 문장에서 골라 서로 겹치지 않게 합니다.
    고를 문장이 부족하면 implications 는 빈 문자열(카드에서 숨김)입니다.
    """
    sents = split_into_sentences(abstract)
    if not sents:
        return [], ""

    implications = ""
    impl_idx = None
    if len(sents) >= 4:
        # 시사점은 보통 초록 후반부에 있으므로 뒤쪽 절반에서만 찾습니다 (배경 문장 오선택 방지)
        for i in range(len(sents) - 1, len(sents) // 2 - 1, -1):
            if IMPLICATION_SIGNAL_RE.search(sents[i]) and len(sents[i]) >= 25:
                implications, impl_idx = sents[i], i
                break

    rest = [s for i, s in enumerate(sents) if i != impl_idx]
    takeaways: List[str] = [rest[0]]
    middle = rest[1:-1]
    data = next((s for s in middle if DATA_SIGNAL_RE.search(s)), None)
    if data is None and middle:
        data = middle[len(middle) // 2]
    if data:
        takeaways.append(data)
    if len(rest) >= 2:
        takeaways.append(rest[-1])

    takeaways = _dedupe(takeaways)
    if implications and any(is_near_duplicate(implications, t) for t in takeaways):
        implications = ""
    return takeaways[:3], implications


def clean_summary(
    takeaways: Iterable[str],
    implications: str,
    abstract: str = "",
) -> Tuple[List[str], str]:
    """
    어떤 출처(AI / 마크다운 / 추출)의 요약이든 마지막에 한 번 통과시키는 정리 함수.
    - "연구 목적:" 같은 템플릿 접두사 제거
    - takeaway 끼리 / 시사점과 takeaway 사이 중복 제거
    - "본 연구는 ~ 근거를 제공합니다" 같은 범용 템플릿 시사점 제거
    - takeaway 가 2개 미만으로 남으면 초록에서 추출 요약으로 보충
    """
    cleaned = [TEMPLATE_PREFIX_RE.sub("", str(t)).strip() for t in (takeaways or [])]
    cleaned = [t for t in cleaned if len(t) >= 10]
    cleaned = _dedupe(cleaned)

    impl = TEMPLATE_PREFIX_RE.sub("", (implications or "")).strip()
    if GENERIC_IMPLICATION_RE.match(impl):
        impl = ""

    if len(cleaned) < 2 and abstract:
        ext_t, ext_i = extractive_summary(abstract)
        cleaned = _dedupe(cleaned + ext_t)[:3]
        if not impl:
            impl = ext_i

    if impl and any(is_near_duplicate(impl, t) for t in cleaned):
        # 시사점이 takeaway 와 같으면, 그 takeaway 를 빼는 대신 시사점을 비웁니다.
        impl = ""
    return cleaned[:3], impl
