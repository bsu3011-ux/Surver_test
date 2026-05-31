#!/bin/bash
# 배포 스크립트 — GitHub Actions 또는 수동 실행
# 실행: bash ~/Surver_test/english_app/deploy.sh
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$REPO_DIR/english_app/frontend"
BRANCH="claude/english-learning-plan-ZwfZ3"

echo "======================================="
echo "  영어 학습 앱 배포 시작"
echo "======================================="

# 1. 최신 코드
echo "[1/3] 최신 코드 가져오는 중..."
git -C "$REPO_DIR" fetch origin
git -C "$REPO_DIR" reset --hard "origin/$BRANCH"
echo "      완료"

# 2. Python 패키지 설치
echo "[2/4] Python 패키지 설치 중..."
pip install fastapi uvicorn groq python-dotenv requests -q
echo "      완료"

# 3. 프론트엔드 빌드
echo "[3/4] 프론트엔드 빌드 중..."
cd "$FRONTEND_DIR"
npm install --silent
npm run build
echo "      완료"

# 4. 서비스 재시작
echo "[4/4] 서비스 재시작 중..."
if systemctl is-active --quiet english-app 2>/dev/null; then
    sudo systemctl restart english-app
    sleep 2
    systemctl is-active --quiet english-app && echo "      서비스 정상 실행 중" || echo "      ⚠️ 재시작 실패. 로그: sudo journalctl -u english-app -n 30"
else
    echo "      ⚠️ systemd 서비스 없음. setup-daemon.sh를 먼저 실행하세요."
    exit 1
fi

echo "======================================="
echo "  배포 완료!"
echo "======================================="
# auto-deploy test Fri May 29 05:59:19 UTC 2026
