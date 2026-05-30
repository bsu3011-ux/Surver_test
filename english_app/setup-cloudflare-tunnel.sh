#!/bin/bash
# Cloudflare Quick Tunnel — 계정·도메인·토큰 없이 자동 설정
set -e

ARCH=$(uname -m)
[ "$ARCH" = "aarch64" ] && ARCH_TAG="arm64" || ARCH_TAG="amd64"
APP_PORT=8002
SERVICE=cf-tunnel
WRAPPER=/usr/local/bin/cf-tunnel-wrapper.sh
URL_FILE=/tmp/cf-url.txt

echo "======================================="
echo "  Cloudflare Quick Tunnel 자동 설정"
echo "======================================="
echo ""

# ── 1. cloudflared 설치 ────────────────────
if command -v cloudflared &>/dev/null; then
  echo "[1/3] cloudflared 이미 설치됨"
else
  echo "[1/3] cloudflared 설치 중 (${ARCH_TAG})..."
  LATEST=$(curl -s https://api.github.com/repos/cloudflare/cloudflared/releases/latest \
    | grep '"tag_name"' | cut -d'"' -f4)
  wget -q "https://github.com/cloudflare/cloudflared/releases/download/${LATEST}/cloudflared-linux-${ARCH_TAG}" \
    -O /tmp/cloudflared
  sudo install -m 0755 /tmp/cloudflared /usr/local/bin/cloudflared
  echo "  완료: $(cloudflared --version | head -1)"
fi

# ── 2. URL 자동 캡처 래퍼 생성 ───────────────
echo "[2/3] URL 캡처 설정 중..."
sudo tee "${WRAPPER}" > /dev/null <<'WRAPPER_EOF'
#!/bin/bash
URL_FILE=/tmp/cf-url.txt
rm -f "$URL_FILE"
/usr/local/bin/cloudflared tunnel --url http://localhost:8002 2>&1 | while IFS= read -r line; do
  echo "$line"
  if [[ "$line" =~ (https://[a-z0-9-]+\.trycloudflare\.com) ]]; then
    echo "${BASH_REMATCH[1]}" > "$URL_FILE"
  fi
done
WRAPPER_EOF
sudo chmod +x "${WRAPPER}"

# ── 3. systemd 서비스 등록 ─────────────────
echo "[3/3] 서비스 등록 중..."

# 이전 설치 정리
sudo systemctl disable --now cloudflared 2>/dev/null || true
sudo systemctl disable --now lt-tunnel    2>/dev/null || true

CURRENT_USER=$(whoami)
sudo tee /etc/systemd/system/${SERVICE}.service > /dev/null <<EOF
[Unit]
Description=Cloudflare Quick Tunnel (english-app :${APP_PORT})
After=network.target english-app.service
Wants=english-app.service

[Service]
User=${CURRENT_USER}
ExecStart=${WRAPPER}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE}
sudo systemctl restart ${SERVICE}

# ── URL 확인 ───────────────────────────────
echo ""
echo "  URL 생성 대기 중..."
for i in $(seq 1 15); do
  sleep 2
  if [ -f "$URL_FILE" ] && [ -s "$URL_FILE" ]; then
    TUNNEL_URL=$(cat "$URL_FILE")
    break
  fi
done

echo ""
echo "======================================="
if [ -n "$TUNNEL_URL" ]; then
  echo "  앱 주소: ${TUNNEL_URL}"
  echo ""
  echo "  ※ 서버 재시작 시 주소가 바뀝니다."
  echo "  다음 접속 후 주소 확인:  cat ${URL_FILE}"
else
  echo "  URL 생성 중... 잠시 후 확인:"
  echo "  cat ${URL_FILE}"
fi
echo "======================================="

# SSH 로그인 때마다 주소 자동 표시 (.bashrc 최초 1회)
if ! grep -q "cf-url.txt" ~/.bashrc 2>/dev/null; then
  cat >> ~/.bashrc <<'BASHRC_EOF'

# 영어 학습 앱 주소
CF_URL=$(cat /tmp/cf-url.txt 2>/dev/null)
[ -n "$CF_URL" ] && echo "📱 앱 주소: $CF_URL"
BASHRC_EOF
  echo ""
  echo "  ✅ 다음부터 SSH 접속 시 주소가 자동으로 표시됩니다."
fi
