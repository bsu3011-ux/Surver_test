#!/bin/bash
# Cloudflare Tunnel 자동 설정 스크립트
# 사전 조건: https://one.dash.cloudflare.com 에서 터널을 먼저 생성해야 합니다.
set -e

ARCH=$(uname -m)
[ "$ARCH" = "aarch64" ] && ARCH_TAG="arm64" || ARCH_TAG="amd64"

echo "======================================="
echo "  Cloudflare Tunnel 설정"
echo "======================================="

# 1. cloudflared 설치
echo ""
echo "[1/3] cloudflared 설치 중 (${ARCH_TAG})..."
LATEST_TAG=$(curl -s https://api.github.com/repos/cloudflare/cloudflared/releases/latest | grep '"tag_name"' | cut -d'"' -f4)
wget -q "https://github.com/cloudflare/cloudflared/releases/download/${LATEST_TAG}/cloudflared-linux-${ARCH_TAG}" -O /tmp/cloudflared
sudo install -m 0755 /tmp/cloudflared /usr/local/bin/cloudflared
echo "  완료: $(cloudflared --version)"

# 2. 터널 토큰 안내
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  아직 터널을 만들지 않았다면:"
echo "  1. https://one.dash.cloudflare.com 접속"
echo "  2. Networks > Tunnels > Add a tunnel"
echo "  3. Cloudflared 선택 > 이름 입력 (예: english-app) > Save"
echo "  4. 'Install and run a connector' 화면에서"
echo "     'cloudflared service install eyJ...' 명령어의 토큰 부분만 복사"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
read -p "터널 토큰을 붙여넣으세요: " TUNNEL_TOKEN

if [ -z "$TUNNEL_TOKEN" ]; then
  echo "토큰이 비어 있습니다. 중단합니다."
  exit 1
fi

# 전체 명령어를 붙여넣었을 경우 토큰만 추출 + 공백/개행 제거
TUNNEL_TOKEN=$(echo "$TUNNEL_TOKEN" | sed 's/.*service install[[:space:]]*//' | tr -d '[:space:]')

# 3. systemd 서비스로 설치
echo ""
echo "[3/3] systemd 서비스 설치 중..."
sudo cloudflared service install "$TUNNEL_TOKEN"
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
sleep 2

if systemctl is-active --quiet cloudflared; then
  echo "  서비스 정상 실행 중 ✅"
else
  echo "  ⚠️ 서비스 시작 실패. 로그 확인:"
  sudo journalctl -u cloudflared -n 20
  exit 1
fi

echo ""
echo "======================================="
echo "  설정 완료!"
echo "  Cloudflare 대시보드에서 URL 확인:"
echo "  https://one.dash.cloudflare.com > Networks > Tunnels"
echo ""
echo "  기존 localtunnel 서비스 제거 (선택):"
echo "  sudo systemctl disable --now lt-tunnel 2>/dev/null || true"
echo "======================================="
