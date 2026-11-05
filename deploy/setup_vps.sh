#!/usr/bin/env bash
# ==============================================================================
# Crypto AI Quantitative Trading - VPS One-Click Production Hardening Setup
# Supported OS: Ubuntu 22.04 / 24.04 LTS, Debian 11 / 12
# Includes: Chrony microsecond time sync, UFW firewall, Fail2ban, Docker hardening
# ==============================================================================

set -e

echo "=================================================================="
echo "  Crypto AI Quantitative Trading - VPS 雲端安全與高精度時鐘初始化"
echo "=================================================================="

if [ "$EUID" -ne 0 ]; then
  SUDO="sudo"
else
  SUDO=""
fi

# 1. Update Packages & Core Tools
echo "[1/6] 更新系統軟體包並安裝基礎工具 (curl, git, tzdata)..."
$SUDO apt-get update -y
$SUDO apt-get install -y curl git tzdata ca-certificates gnupg

# 2. Timezone & Chrony Microsecond Clock Sync (CRITICAL for exchange signatures)
echo "[2/6] 配置時區 (Asia/Taipei) 與安裝 Chrony 高精度時鐘同步..."
$SUDO timedatectl set-timezone Asia/Taipei || true
$SUDO apt-get install -y chrony
$SUDO systemctl enable --now chrony
$SUDO chronyc makestep || true
echo "時鐘同步狀態："
$SUDO chronyc tracking || true

# 3. Security Hardening: UFW Firewall (Zero Ingress, Outbound Only)
echo "[3/6] 配置 UFW 嚴密防火牆 (全面封鎖外來連線，零開放埠號)..."
$SUDO apt-get install -y ufw
$SUDO ufw default deny incoming
$SUDO ufw default allow outgoing
$SUDO ufw allow 22/tcp comment 'SSH Management'
$SUDO ufw --force enable
echo "UFW 防火牆狀態："
$SUDO ufw status verbose

# 4. Security Hardening: Fail2ban (Anti SSH Brute-Force)
echo "[4/6] 安裝並啟動 fail2ban (防止 SSH 暴力密碼破解)..."
$SUDO apt-get install -y fail2ban
$SUDO systemctl enable --now fail2ban

# 5. Install Docker & Compose Plugin
if ! command -v docker &> /dev/null; then
    echo "[5/6] 正在自動安裝 Docker 與 Docker Compose 插件..."
    curl -fsSL https://get.docker.com | $SUDO sh
    $SUDO usermod -aG docker "$USER" || true
    echo "Docker 安裝完成！"
else
    echo "[5/6] Docker 已安裝，略過安裝步驟。"
fi

# 6. Prepare Application Directories & .env Permission Hardening
echo "[6/6] 檢查專案目錄與權限加固..."
mkdir -p data journals logs journals/reports/daily journals/reports/weekly
chmod 700 deploy/ || true

if [ ! -f ".env" ]; then
    echo ""
    echo "⚠️  尚未偵測到 .env 檔案！"
    echo "正在從 .env.example 建立範本..."
    cp .env.example .env
    chmod 600 .env
    echo ""
    echo "=================================================================="
    echo "【重要提示】請立即執行以下指令編輯 .env 並填入您的金鑰："
    echo "   nano .env"
    echo "填寫完成後，執行以下指令即可全自動在背景啟動操盤："
    echo "   docker compose up -d --build"
    echo "=================================================================="
else
    chmod 600 .env
    echo "✅ .env 檔案已存在，已鎖定權限為 600 (僅擁有者可讀寫)。"
    echo ""
    echo "=================================================================="
    echo "【準備就緒】您可以隨時執行以下指令啟動雲端操盤："
    echo "   docker compose up -d --build"
    echo "查看運行日誌："
    echo "   docker compose logs -f"
    echo "=================================================================="
fi
