#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phyco & Blue Carbon Automation All-in-One Runner
- 논문 수집(fetch_and_archive.py) 및 웹진 빌드(build_site.py)를 한 번에 실행합니다.
- 매주 수요일 로컬 또는 CI 환경에서 단일 명령어로 동작 가능
"""

import sys
import subprocess
from pathlib import Path

# Windows 콘솔 및 다국어 출력을 위한 UTF-8 강제 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"


def run_command(command, desc):
    print(f"\n==================================================")
    print(f"▶ {desc} 시작...")
    print(f"명령어: {' '.join(command)}")
    print(f"==================================================")
    result = subprocess.run(command, cwd=BASE_DIR)
    if result.returncode != 0:
        print(f"[-] {desc} 중 에러가 발생했습니다. (Exit code: {result.returncode})")
        return False
    print(f"[+] {desc} 성공적으로 완료되었습니다.")
    return True


def main():
    python_bin = sys.executable

    # 1. 논문 수집 및 마크다운 저장
    success_fetch = run_command(
        [python_bin, str(SCRIPTS_DIR / "fetch_and_archive.py")],
        "최신 해조류 및 블루카본 논문 수집 및 아카이빙"
    )
    if not success_fetch:
        print("[-] 수집 단계 실패로 인해 파이프라인을 중단합니다.")
        sys.exit(1)

    # 2. 정적 웹진 HTML 빌드
    success_build = run_command(
        [python_bin, str(SCRIPTS_DIR / "build_site.py")],
        "모던 웹진 블로그(HTML) 정적 빌드"
    )
    if not success_build:
        print("[-] 빌드 단계 실패로 인해 파이프라인을 중단합니다.")
        sys.exit(1)

    print("\n🎉 모든 파이프라인이 정상적으로 완료되었습니다!")
    print("👉 public/index.html 파일을 브라우저로 열거나 Vercel에 배포하여 확인하세요.")


if __name__ == "__main__":
    main()
