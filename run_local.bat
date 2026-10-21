@echo off
chcp 65001 > nul
setlocal
cd /d "%~dp0"
echo ==================================================
echo  Phyco ^& Blue Carbon - 로컬 테스트 빌드 (GitHub 에 올리지 않음)
echo ==================================================

if not exist venv\Scripts\python.exe (
    echo   venv 가 없어 새로 만듭니다.
    py -3.11 -m venv venv 2>nul || python -m venv venv
    if errorlevel 1 goto :fail
)
venv\Scripts\python.exe -m pip install -q -r requirements.txt
if errorlevel 1 goto :fail

echo [1/2] 논문 수집 및 요약...
venv\Scripts\python.exe scripts\fetch_and_archive.py
if errorlevel 1 goto :fail

echo [2/2] 사이트 빌드...
venv\Scripts\python.exe scripts\build_site.py
if errorlevel 1 goto :fail

echo ==================================================
echo  완료! public\index.html 을 브라우저로 열어 확인하세요.
echo  주의: 수집 상태(data\)와 아카이브가 바뀌었습니다. 올리려면 deploy.bat 을 쓰세요.
echo ==================================================
pause
exit /b 0

:fail
echo  [오류] 실패해 중단했습니다.
pause
exit /b 1
