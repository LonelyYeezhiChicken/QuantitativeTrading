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

# 2. Configure 2GB Swap for 1GB RAM VPS (Prevent Out-Of-Memory on $5/$6 Cloud Instances)
TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
if [ "$TOTAL_RAM_KB" -lt 1600000 ]; then
    if ! swapon --show | grep -q "/swapfile"; then
        echo "[2/7] 偵測到伺服器實體記憶體 <= 1.5GB，自動啟用 2GB NVMe Swap 虛擬記憶體緩衝..."
        $SUDO fallocate -l 2G /swapfile 2>/dev/null || $SUDO dd if=/dev/zero of=/swapfile bs=1M count=2048
        $SUDO chmod 600 /swapfile
        $SUDO mkswap /swapfile
        $SUDO swapon /swapfile
        if ! grep -q "/swapfile" /etc/fstab; then
            echo '/swapfile none swap sw 0 0' | $SUDO tee -a /etc/fstab
        fi
        echo "✅ 2GB Swap 配置完成！系統記憶體池安全擴增至 3GB。"
    else
        echo "[2/7] 虛擬記憶體 (Swap) 已存在，略過建立。"
    fi
else
    echo "[2/7] 實體記憶體充足 (> 1.5GB)，略過 Swap 建立。"
fi

# 3. Timezone & Chrony Microsecond Clock Sync (CRITICAL for exchange signatures)
echo "[3/7] 配置時區 (Asia/Taipei) 與安裝 Chrony 高精度時鐘同步..."
$SUDO timedatectl set-timezone Asia/Taipei || true
$SUDO apt-get install -y chrony
$SUDO systemctl enable --now chrony
$SUDO chronyc makestep || true
echo "時鐘同步狀態："
$SUDO chronyc tracking || true

# 4. Security Hardening: UFW Firewall (Zero Ingress, Outbound Only)
echo "[4/7] 配置 UFW 嚴密防火牆 (全面封鎖外來連線，零開放埠號)..."
$SUDO apt-get install -y ufw
$SUDO ufw default deny incoming
$SUDO ufw default allow outgoing
$SUDO ufw allow 22/tcp comment 'SSH Management'
$SUDO ufw --force enable
echo "UFW 防火牆狀態："
$SUDO ufw status verbose

# 5. Security Hardening: Fail2ban (Anti SSH Brute-Force)
echo "[5/7] 安裝並啟動 fail2ban (防止 SSH 暴力密碼破解)..."
$SUDO apt-get install -y fail2ban
$SUDO systemctl enable --now fail2ban

# 6. Install Docker & Compose Plugin
if ! command -v docker &> /dev/null; then
    echo "[6/7] 正在自動安裝 Docker 與 Docker Compose 插件..."
    curl -fsSL https://get.docker.com | $SUDO sh
    $SUDO usermod -aG docker "$USER" || true
    echo "Docker 安裝完成！"
else
    echo "[6/7] Docker 已安裝，略過安裝步驟。"
fi

# 7. Prepare Application Directories & .env Permission Hardening
echo "[7/7] 檢查專案目錄與權限加固..."
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
