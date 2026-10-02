# 🌊 김/바다고리풀속 및 블루카본 연구 매거진 & 아카이브 자동화 시스템
> **Phyco & Blue Carbon Research Magazine and Dual Archiving System**  
> 학명 개정과 신분류 체계(*Pyropia*, *Porphyra*, *Neopyropia*, *Neoporphyra*, *Phycocalidia*, *Asparagopsis*)를 반영한 해조류 생물학 및 해양 블루카본 연구 주간 자동 수집·분석·웹진 발행 파이프라인

[![Weekly Pipeline](https://github.com/your-username/phyco-research-archive/actions/workflows/weekly-pipeline.yml/badge.svg)](https://github.com)
[![Vercel Deployment](https://img.shields.io/badge/Vercel-Deployed-black?logo=vercel)](https://vercel.com)
[![Schedule](https://img.shields.io/badge/Schedule-Every%20Wednesday%2009:00%20KST-0d9488)](#)

---

## 🌟 프로젝트 개요

본 프로젝트는 개인 연구자 및 연구 그룹을 위한 **연구 아카이브 자동화 시스템**입니다. 매주 수요일마다 글로벌 오픈 사이언스 데이터베이스(NCBI PubMed, Europe PMC 등)에서 최신 논문을 자동 수집하여, 영구 데이터 분석 및 검색을 위한 **Markdown 아카이브(`/archives/`)**와 모바일/PC에 최적화된 **모던 웹진 블로그(`public/index.html`)**로 동시 빌드 및 퍼블리싱합니다.

---

## 📁 프로젝트 구조 (Directory Structure)

```text
phyco-research-archive/
├── .github/
│   └── workflows/
│       └── weekly-pipeline.yml    # [요구사항 4] 매주 수요일 자동 실행 GitHub Actions
├── archives/                      # [요구사항 2] 영구 보존용 주간 연구 분석 Markdown
│   ├── 2026-09-30-weekly-digest.md# 초기 검증용 샘플 아카이브
│   └── YYYY-MM-DD-weekly-digest.md# 매주 수요일 자동 누적되는 아카이브
├── keywords.json                  # [요구사항 1] 생물군 및 3대 연구 카테고리 키워드 설정
├── public/                        # [요구사항 2, 3] Vercel 배포용 정적 웹사이트 루트
│   ├── index.html                 # 반응형 모던 매거진 블로그 (Tailwind CSS, Lucide Icons)
│   └── data/
│       ├── archives-index.json    # 주차별 아카이브 색인 데이터
│       └── latest-articles.json   # 최신 논문 메타데이터
├── scripts/
│   ├── fetch_and_archive.py       # 최신 논문 수집, AI 브리핑, Markdown 생성 스크립트
│   ├── build_site.py              # Markdown을 파싱하여 정적 웹진(HTML)으로 빌드
│   └── run_all.py                 # 수집부터 사이트 빌드까지 원클릭 실행 스크립트
├── vercel.json                    # [요구사항 3] Vercel 클라우드 배포 설정 파일
├── package.json                   # npm 편의 스크립트 및 프로젝트 메타정보
├── requirements.txt               # 파이썬 의존성 패키지 목록
├── .gitignore                     # Git 형상관리 제외 설정
└── README.md                      # 프로젝트 상세 설명서
```

---

## ⚙️ 4대 핵심 기능 및 시스템 설계

### 1. 🗂️ 키워드 설정 분리 (`keywords.json`)
언제든 새로운 연구 키워드나 분류학적 학명 변동을 자유롭게 수정·확장할 수 있습니다.
- **대상 생물군 (Target Taxa)**:
  - `Pyropia` (참김/광의의 김속)
  - `Porphyra` (전통 원형 김속)
  - `Neopyropia` (방사무늬김 등 신김속)
  - `Neoporphyra` (모무늬돌김 등 신포르피라속)
  - `Phycocalidia` (피코칼리디아속 열대/아열대성 엽상 홍조류)
  - `Asparagopsis` (바다고리풀속, 저메탄 가축사료 핵심종)
- **3대 연구 카테고리**:
  1. `breeding_molecular_pathology`: 육종 · 분자생물학 · 붉은갯병/녹반병 등 병해
  2. `thallus_lifecycle_cultivation`: 엽체 생리 · 사상체(Conchocelis)/생활사 · 스마트 양식 및 배양
  3. `blue_carbon_feed_methane`: 해양 블루카본 탄소격리 · 반추위 메탄 저감 사료 첨가제(브로모포름)

### 2. 📑 듀얼 아카이빙 시스템 (Markdown + 전문 학술 매거진 블로그)
- **Markdown 영구 아카이브 (`/archives/`)**:
  - 매주 수요일 수집된 논문이 YAML Frontmatter와 구조화된 GFM Markdown 형식으로 자동 저장됩니다.
  - 논문별 직관적 헤드라인, 3대 핵심 성과(Key Takeaways), 연구자 시사점, 썸네일 이미지 및 원문 초록이 온전히 보존됩니다.
  - Obsidian, Notion, 로컬 벡터 DB, RAG 파이프라인에 즉시 활용 가능합니다.
- **전문 학술 매거진 웹페이지 (`public/index.html`)**:
  - **요약 중심 UI/UX**: 복잡한 초록 대신 ① 직관적인 한 줄 헤드라인, ② 3가지 핵심 요약 포인트, ③ 연구자 시사점만 카드에 일목요연하게 노출.
  - **접이식 초록 토글**: `[초록 원문 보기]` 버튼 클릭 시에만 세련된 아코디언 스타일로 초록 전문 열람.
  - **3대 섹션별 완벽 분리 & Editor's Weekly Insight**:
    - 🧬 `SECTION 01. 육종 · 분자생물학 · 병해`
    - 🌱 `SECTION 02. 엽체 생리 · 생활사 · 스마트 양식`
    - 🌍 `SECTION 03. 블루카본 · 저메탄 사료 · 기후대응`
    - 각 섹션 상단에 이번 주 해당 분야의 핵심 트렌드를 짚어주는 큐레이션 브리핑 박스 제공.
  - **매거진 비주얼 썸네일**: 논문 주제와 1:1로 어울리는 고해상도 해양·바이오풍 사이언스 대표 썸네일 이미지 매칭.
  - **스티키 섹션 네비게이터 & 실시간 필터**: 상단 앵커 점프 바, 생물군별 원클릭 필터, 실시간 통합 검색 지원.

### 3. ☁️ Vercel 퍼블리싱 준비 (`vercel.json`)
- Vercel의 글로벌 Edge CDN을 통해 별도의 서버 호스팅 비용 없이 100% 무료로 무중단 배포됩니다.
- GitHub에 커밋이 푸시될 때마다 Vercel이 변경된 `public/` 디렉토리를 감지하여 몇 초 내에 자동 배포합니다.
- `my-phyco-archive.vercel.app` 형태의 고유 URL 제공.

### 4. ⏰ 매주 수요일 자동화 스케줄러 (`.github/workflows/weekly-pipeline.yml`)
- 매주 수요일 UTC 00:00 (한국 시간 기준 **수요일 오전 09:00 KST**)에 GitHub Actions가 자동 실행됩니다.
- 최신 논문을 수집하고 마크다운과 웹페이지를 빌드한 후, 자동으로 저장소의 `main` 브랜치에 커밋 & 푸시합니다.
- GitHub 저장소의 **Actions** 탭에서 언제든 `Run workflow` 버튼으로 수동 즉시 실행도 가능합니다.

---

## 🚀 빠른 시작 가이드 (Quick Start)

### 로컬 환경에서 실행하기

1. **저장소 클론 또는 프로젝트 폴더로 이동**:
   ```bash
   cd C:\Users\user\.gemini\antigravity\scratch\phyco-research-archive
   ```

2. **파이썬 환경 및 패키지 설치**:
   ```bash
   pip install -r requirements.txt
   ```

3. **원클릭 파이프라인 실행 (수집 + 웹진 빌드)**:
   ```bash
   python scripts/run_all.py
   ```
   > 개별 실행 시:
   > - 논문 수집 및 마크다운 생성: `python scripts/fetch_and_archive.py`
   > - 웹진 HTML 빌드: `python scripts/build_site.py`

4. **로컬 웹페이지 미리보기**:
   `public/index.html` 파일을 더블클릭하여 브라우저에서 바로 열거나 로컬 서버 실행:
   ```bash
   npx serve public
   # 또는
   python -m http.server 3000 --directory public
   ```
   브라우저에서 `http://localhost:3000` 접속.

---

## 🌐 GitHub & Vercel 배포 방법 (Step-by-Step)

### Step 1. GitHub 저장소 생성 및 푸시
1. GitHub(https://github.com)에서 새 비공개(또는 공개) 저장소 `phyco-research-archive`를 생성합니다.
2. 로컬 터미널에서 다음 명령어로 푸시합니다:
   ```bash
   git init
   git add .
   git commit -m "feat: initial commit for phyco research archive system"
   git branch -M main
   git remote add origin https://github.com/<YOUR-GITHUB-ID>/phyco-research-archive.git
   git push -u origin main
   ```

### Step 2. Vercel 연동
1. [Vercel](https://vercel.com)에 로그인 후 **"Add New..."** > **"Project"** 클릭.
2. 방금 올린 GitHub 저장소(`phyco-research-archive`)를 **Import**합니다.
3. 배포 설정:
   - **Framework Preset**: `Other`
   - **Root Directory**: `./` (기본값)
   - **Output Directory**: `public` (이미 `vercel.json`에 정의되어 있어 자동 인식됨)
4. **"Deploy"** 버튼 클릭! 10초 내로 전 세계에 배포된 나만의 매거진 링크가 생성됩니다.

### Step 3. (선택사항) Gemini API 심층 분석 설정
논문의 영문 초록을 단순 발췌하는 것을 넘어, 구글 Gemini AI 모델이 **전문적인 한국어 심층 요약 및 산업적 시사점**을 자동 생성하도록 설정할 수 있습니다.
1. [Google AI Studio](https://aistudio.google.com/)에서 Gemini API Key를 발급받습니다.
2. GitHub 저장소 > **Settings** > **Secrets and variables** > **Actions** > **New repository secret** 클릭.
3. Name: `GEMINI_API_KEY`, Secret: `발급받은 키` 입력 후 저장.
4. 이후 매주 수요일 자동 파이프라인에서 최고 품질의 AI 연구 브리핑이 자동 반영됩니다. (API 키가 없어도 PubMed 원문 기반 규칙 요약으로 안정 작동합니다.)

---

## 🛠️ 키워드 및 설정 커스터마이징

새로운 생물종이나 관심 키워드를 추가하고 싶다면 `keywords.json` 파일만 수정하면 됩니다:
```json
{
  "target_taxa": {
    "genera": [
      {
        "name": "Pyropia",
        "aliases": ["Pyropia yezoensis", "Pyropia tenera"],
        "enabled": true
      }
    ]
  },
  "research_categories": {
    "blue_carbon_feed_methane": {
      "keywords": ["blue carbon", "methane reduction", "bromoform"]
    }
  }
}
```

---

## 📜 라이선스
MIT License. 자유롭게 연구 및 상업용 프로젝트에 수정하여 활용하실 수 있습니다.
