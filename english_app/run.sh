#!/bin/bash
# ============================================================
# 단일 포트 실행 스크립트 (배포/터널용)
# 프론트엔드를 빌드해 FastAPI(8002)가 통째로 서빙한다.
# 포트 1개만 열면 되므로 터널(cloudflared, localtunnel 등)이 단순해진다.
# ============================================================
set -e
cd "$(dirname "$0")"

PORT=8002

echo "🧹 기존 프로세스 종료..."
fuser -k ${PORT}/tcp 2>/dev/null || true
sleep 1

# .env 로드 (상위 디렉토리)
if [ -f "../.env" ]; then
  set -a
  . ../.env
  set +a
fi

echo "📦 백엔드 의존성 설치..."
pip install fastapi uvicorn anthropic python-dotenv requests -q

echo "📦 프론트엔드 빌드 (최초 1회는 시간이 걸립니다)..."
cd frontend
npm install --silent
npm run build
cd ..

SERVER_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "✅ 앱 실행: http://localhost:${PORT}"
echo "🌐 내부망:  http://${SERVER_IP}:${PORT}"
echo ""
echo "📱 외부(폰)에서 열려면 새 터미널에서:"
echo "   npx localtunnel --port ${PORT}"
echo "   또는  ./cloudflared tunnel --url http://localhost:${PORT}"
echo ""
echo "Ctrl+C로 종료"

cd backend
exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
