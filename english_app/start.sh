#!/bin/bash
echo "🚀 영어 학습 앱 시작..."
cd "$(dirname "$0")"

# 기존 프로세스 정리
echo "🧹 기존 프로세스 종료 중..."
fuser -k 8000/tcp 2>/dev/null || true
fuser -k 5173/tcp 2>/dev/null || true
sleep 1

# .env 파일 로드 (상위 디렉토리)
if [ -f "../.env" ]; then
  export $(grep -v '^#' ../.env | xargs)
fi

# Install backend deps
cd backend
pip install fastapi uvicorn anthropic python-dotenv requests -q
cd ..

# Install frontend deps
cd frontend
npm install --silent
cd ..

# 서버 IP 안내
SERVER_IP=$(hostname -I | awk '{print $1}')

# Start backend
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

# Start frontend
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!
cd ..

sleep 3
echo ""
echo "✅ 백엔드:    http://localhost:8000"
echo "✅ 프론트엔드: http://localhost:5173"
echo "🌐 외부 접속:  http://${SERVER_IP}:5173"
echo ""
echo "Ctrl+C로 종료"
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT
wait
