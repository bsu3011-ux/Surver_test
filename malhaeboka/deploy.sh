#!/bin/bash
# GitHub 웹훅 트리거 시 자동 실행되는 배포 스크립트

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$REPO_DIR/malhaeboka"
LOG="$APP_DIR/deploy.log"
BRANCH="${DEPLOY_BRANCH:-claude/malheboka-structure-analysis-GedwO}"
PORT="${PORT:-8002}"

echo "" >> "$LOG"
echo "========================================" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 배포 시작" >> "$LOG"

# 1. 코드 업데이트
cd "$REPO_DIR"
echo "[git] fetch & pull..." >> "$LOG"
git fetch origin "$BRANCH" >> "$LOG" 2>&1
git checkout "$BRANCH" >> "$LOG" 2>&1
git pull origin "$BRANCH" >> "$LOG" 2>&1

# 2. 의존성 설치 (새 패키지 추가된 경우)
if [ -f "$REPO_DIR/requirements.txt" ]; then
    pip install -q -r "$REPO_DIR/requirements.txt" >> "$LOG" 2>&1
fi
pip install -q fastapi "uvicorn[standard]" >> "$LOG" 2>&1

# 3. 기존 프로세스 종료
OLD_PID=$(lsof -t -i:$PORT 2>/dev/null)
if [ -n "$OLD_PID" ]; then
    echo "[kill] 기존 프로세스 $OLD_PID 종료" >> "$LOG"
    kill "$OLD_PID"
    sleep 2
fi

# 4. 서버 재시작 (백그라운드)
cd "$APP_DIR"
nohup python3 -m uvicorn main:app \
    --host 0.0.0.0 \
    --port $PORT \
    --reload >> "$LOG" 2>&1 &

NEW_PID=$!
echo "[start] 새 서버 PID=$NEW_PID, 포트=$PORT" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 배포 완료" >> "$LOG"
