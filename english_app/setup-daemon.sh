#!/bin/bash
# 최초 1회 실행: systemd 서비스 등록 + GitHub Actions용 SSH 키 생성
# 실행: bash ~/Surver_test/english_app/setup-daemon.sh

set -e
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$REPO_DIR/english_app"
ENV_FILE="$REPO_DIR/.env"
CURRENT_USER=$(whoami)
PYTHON=$(which python3)
NODE=$(which node)
NPM=$(which npm)

echo "======================================="
echo "  영어 학습 앱 데몬 설정"
echo "======================================="

# ── 1. 프론트엔드 최초 빌드 ────────────────────────────────────────
echo "[1/4] 프론트엔드 빌드 중..."
cd "$APP_DIR/frontend"
npm install --silent
npm run build
echo "      완료"

# ── 2. systemd 서비스 등록 ─────────────────────────────────────────
echo "[2/4] systemd 서비스 등록 중..."

sudo tee /etc/systemd/system/english-app.service > /dev/null << UNIT
[Unit]
Description=English Learning App (FastAPI + React)
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$APP_DIR/backend
EnvironmentFile=$ENV_FILE
ExecStart=$PYTHON -m uvicorn main:app --host 0.0.0.0 --port 8002
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable english-app
sudo systemctl restart english-app
sleep 2
systemctl is-active --quiet english-app && echo "      서비스 실행 중 ✅" || echo "      ⚠️  실행 실패 — 로그: sudo journalctl -u english-app -n 30"

# ── 3. deploy.sh 가 sudo restart 할 수 있도록 권한 설정 ─────────────
echo "[3/4] 자동 재시작 권한 설정 중..."
echo "$CURRENT_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart english-app" \
    | sudo tee /etc/sudoers.d/english-app > /dev/null
sudo chmod 440 /etc/sudoers.d/english-app
echo "      완료"

# ── 4. GitHub Actions 용 SSH 키 생성 ───────────────────────────────
echo "[4/4] GitHub Actions SSH 키 생성 중..."
KEY_FILE="$HOME/.ssh/github_actions_deploy"

if [ ! -f "$KEY_FILE" ]; then
    ssh-keygen -t ed25519 -C "github-actions-deploy" -f "$KEY_FILE" -N ""
fi

# 공개키를 authorized_keys 에 추가 (중복 방지)
PUB_KEY=$(cat "${KEY_FILE}.pub")
if ! grep -qF "$PUB_KEY" "$HOME/.ssh/authorized_keys" 2>/dev/null; then
    echo "$PUB_KEY" >> "$HOME/.ssh/authorized_keys"
    chmod 600 "$HOME/.ssh/authorized_keys"
fi

echo ""
echo "======================================="
echo "  설정 완료!"
echo "======================================="
echo ""
echo "📋 GitHub Actions 설정 (아래 3개를 GitHub Secrets에 등록)"
echo ""
echo "  [1] Settings → Secrets → Actions → New repository secret"
echo ""
echo "  Secret 이름: DEPLOY_HOST"
echo "  Secret 값:   $(curl -s ifconfig.me 2>/dev/null || echo '서버공인IP')"
echo ""
echo "  Secret 이름: DEPLOY_USER"
echo "  Secret 값:   $CURRENT_USER"
echo ""
echo "  Secret 이름: DEPLOY_SSH_KEY"
echo "  Secret 값:   (아래 키 전체 복사 — BEGIN부터 END까지)"
echo ""
cat "$KEY_FILE"
echo ""
echo "======================================="
echo "  유용한 명령어"
echo "======================================="
echo "  상태 확인:  sudo systemctl status english-app"
echo "  로그 보기:  sudo journalctl -u english-app -f"
echo "  수동 배포:  bash $APP_DIR/deploy.sh"
echo "======================================="
