#!/bin/bash
# 말해보카 서버 시작 스크립트
# 사용법: bash start.sh

REPO_URL="https://github.com/bsu3011-ux/Surver_test.git"
BRANCH="claude/malheboka-structure-analysis-GedwO"
INSTALL_DIR="$HOME/Surver_test"
APP_DIR="$INSTALL_DIR/malhaeboka"
PORT=8002
LOG="$APP_DIR/server.log"

echo "🔧 말해보카 서버 시작..."

# 1. 저장소 클론 or 업데이트
if [ ! -d "$INSTALL_DIR/.git" ]; then
  echo "📥 저장소 클론 중..."
  git clone "$REPO_URL" "$INSTALL_DIR"
  cd "$INSTALL_DIR"
  git checkout "$BRANCH"
else
  echo "🔄 코드 업데이트 중..."
  cd "$INSTALL_DIR"
  git fetch origin
  git checkout "$BRANCH"
  git pull origin "$BRANCH"
fi

# 2. 의존성 설치
echo "📦 의존성 설치 중..."
pip install fastapi "uvicorn[standard]" -q

# 3. 기존 서버 종료
OLD=$(lsof -t -i:$PORT 2>/dev/null)
if [ -n "$OLD" ]; then
  echo "⏹️  기존 서버 종료 (PID: $OLD)"
  kill "$OLD" 2>/dev/null
  sleep 2
fi

# 4. 서버 시작
cd "$APP_DIR"
echo "🚀 서버 시작 (포트 $PORT)..."
nohup python3 -m uvicorn main:app \
  --host 0.0.0.0 \
  --port $PORT \
  --reload > "$LOG" 2>&1 &

echo "✅ 완료! PID=$!"
echo "📋 로그: tail -f $LOG"
echo "🌐 접속: http://$(hostname -I | awk '{print $1}'):$PORT"
