@echo off
:: 인코딩을 UTF-8로 설정
chcp 65001 > nul

echo [0/4] 가상환경 활성화 중...
call venv\Scripts\activate.bat

echo [1/4] 최신 논문 데이터 수집 중...
python scripts\fetch_and_archive.py

echo [2/4] 정적 사이트(HTML) 빌드 중...
python scripts\build_site.py

echo [3/4] 변경된 파일 Git에 스테이징 중...
git add .

echo [4/4] GitHub로 변경사항 푸시 중 (Vercel 자동 배포 트리거)...
git commit -m "Auto-update: Research archive sync"
git push origin main

echo 모든 작업이 완료되었습니다! 잠시 후 Vercel에 반영됩니다.
pause