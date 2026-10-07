@echo off
:: 인코딩을 UTF-8로 설정
chcp 65001 > nul

echo [0/6] 가상환경 활성화 중...
call venv\Scripts\activate.bat

echo [1/6] 원격 저장소의 최신 내용 동기화 (Pull) 중...
git pull origin main --rebase

echo [2/6] 최신 논문 데이터 수집 중...
python scripts\fetch_and_archive.py

echo [3/6] 정적 사이트(HTML) 빌드 중...
python scripts\build_site.py

echo [4/6] 변경된 파일 Git에 스테이징 중...
git add .

echo [5/6] 로컬 커밋 생성 중...
git commit -m "Auto-update: Research archive sync"

echo [6/6] GitHub로 변경사항 푸시 중 (Vercel 자동 배포 트리거)...
git push origin main

echo 모든 작업이 완료되었습니다! 잠시 후 Vercel에 반영됩니다.
pause