@echo off
chcp 65001 > nul
setlocal
cd /d "%~dp0"
echo ==================================================
echo  Phyco ^& Blue Carbon - 수동 발행 및 배포
echo  (정기 발행은 GitHub Actions 가 2주마다 자동으로 합니다.
echo   이 파일은 코드 수정 후 올리거나, 지금 바로 발행할 때 씁니다.)
echo ==================================================

echo [1/6] 가상환경 확인...
if not exist venv\Scripts\python.exe (
    echo   venv 가 없어 새로 만듭니다.
    py -3.11 -m venv venv 2>nul || python -m venv venv
    if errorlevel 1 goto :fail
)
venv\Scripts\python.exe -m pip install -q -r requirements.txt
if errorlevel 1 goto :fail

echo [2/6] GitHub 최신 내용 받기 (Actions 가 올린 호 포함)...
git pull --rebase --autostash origin main
if errorlevel 1 goto :fail

echo [3/6] 논문 수집 및 요약...
venv\Scripts\python.exe scripts\fetch_and_archive.py
if errorlevel 1 goto :fail

echo [4/6] 사이트 빌드...
venv\Scripts\python.exe scripts\build_site.py
if errorlevel 1 goto :fail

echo [5/6] 커밋 (코드 + 아카이브 + 사이트 + 수집 상태)...
git add scripts\ keywords.json requirements.txt .github\ archives\ public\ data\ deploy.bat run_local.bat vercel.json
if exist summary_cache.json git add summary_cache.json
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "Manual publish: research archive and site update"
    if errorlevel 1 goto :fail
) else (
    echo   변경사항이 없습니다.
)

echo [6/6] GitHub 로 푸시 (Vercel 자동 배포)...
git push origin main
if errorlevel 1 goto :fail

echo ==================================================
echo  완료! 잠시 후 Vercel 에 반영됩니다.
echo ==================================================
pause
exit /b 0

:fail
echo.
echo ==================================================
echo  [오류] 위 단계에서 실패해 중단했습니다. 메시지를 확인해 주세요.
echo ==================================================
pause
exit /b 1
