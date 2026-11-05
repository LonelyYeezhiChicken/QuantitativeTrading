# 雲端伺服器 (VPS) 24/7 永續合約操盤部署指南

本手冊為將量化交易系統（3x、10x、50x 實盤機器人 + 定時日報排程）遷移至 24/7 雲端伺服器的權威部署與安全加固文檔。

---

## 1. 為什麼選擇 VPS 雲端部署？

* **永不停機**：不怕 Windows Update 自動重開機、筆電休眠、斷電或家用 Wi-Fi 斷線。
* **超低延遲**：選擇新加坡或東京機房，與 BingX 撮合引擎處於同區域，延遲縮短至 **5 ~ 15ms**。
* **筆電解放**：隨時闔蓋出門、關機休眠，不干擾雲端自主操盤。
* **低成本**：本專案採用輕量高效率架構，僅需 **1 vCPU / 1GB 或 2GB RAM**（每月約 $3.5 ~ $5 USD，約台幣 110 ~ 160 元）。

---

## 2. 雲端平台選購建議

推薦各大知名雲端平台（任選一家即可）：
1. **AWS Lightsail (亞馬遜)**：
   * **規格**：1 vCPU / 1GB RAM / 40GB SSD
   * **地區 (Region)**：`ap-southeast-1 (Singapore)` 或 `ap-northeast-1 (Tokyo)`
   * **價格**：約 $3.5 USD / 月（新用戶有免費試用期）
2. **DigitalOcean**：
   * **規格**：Basic Droplet (1 vCPU / 1GB 或 2GB RAM)
   * **地區**：Singapore (SGP1)
   * **價格**：$4 ~ $6 USD / 月
3. **Vultr**：
   * **規格**：Cloud Compute (1 vCPU / 1GB RAM)
   * **地區**：Singapore / Tokyo
   * **價格**：$5 USD / 月

> 作業系統一律建議選擇：**Ubuntu 22.04 LTS** 或 **Ubuntu 24.04 LTS** (64-bit)。

---

## 3. 三步驟一鍵部署流程 (Docker 方式，最推薦)

### 第一步：連接到你的 VPS
使用終端機（PowerShell 或 Mac Terminal）SSH 登入伺服器：
```bash
ssh ubuntu@你的伺服器IP
```

### 第二步：抓取專案並執行初始化腳本
```bash
git clone https://github.com/LonelyYeezhiChicken/QuantitativeTrading.git
cd QuantitativeTrading
bash deploy/setup_vps.sh
```
初始化腳本會全自動完成：
* 更新 Ubuntu 系統套件
* 安裝並啟用 **`chrony` 微秒級高精度時鐘同步**（杜絕下單時間戳失效）
* 將系統時區配置為 `Asia/Taipei (UTC+8)`
* 啟用 **`UFW` 全閉鎖防火牆**（封鎖全部外來埠號，僅開 SSH）
* 安裝並啟動 **`fail2ban` 防暴力破解守護**（自動封鎖惡意登入）
* 自動安裝最新版 Docker 與 Docker Compose 插件
* 從 `.env.example` 複製出 `.env` 檔案範本並鎖定權限為 `600`

### 第三步：設定私密金鑰 `.env` 並啟動
使用 `nano` 編輯環境變數：
```bash
nano .env
```
填入您的真實金鑰（**注意：切勿將 `.env` 提交或推送到任何 Git 倉庫**）：
```env
BINGX_API_KEY=您的BingX_API_Key
BINGX_API_SECRET=您的BingX_API_Secret

# 雲端 AI 決策 API (推薦 Google Gemini，每月有免費額度)
AI_PROVIDER=gemini
AI_DECISION_TIMEOUT_SEC=2.0
GEMINI_API_KEY=您的Gemini_API_Key
```
按 `Ctrl + O` 存檔，按 `Enter` 確認，再按 `Ctrl + X` 離開。

輸入以下指令，全自動建置鏡像並在背景啟動所有守護進程：
```bash
docker compose up -d --build
```

---

## 4. 上雲雙重安全核心：時間校準與伺服器防禦

### 一、時間精確防護（杜絕下單拒絕與報表錯位）
1. **Chrony 微秒級時鐘守護**：
   * 加密貨幣交易所（BingX）的簽名機制要求請求時間戳誤差在 `1000~5000ms` 內。若雲端虛擬機時間漂移超過 2 秒，下單端點會報 `timestamp expired`。
   * 本專案在 VPS 自動裝設 `chrony` 與全域 NTP 伺服器對時，漂移控制在 `0.001` 秒以內。
2. **客戶端動態原子校正 (Clock-Skew Auto-Calibration)**：
   * 在 [`BingXClient`](file:///C:/code/AIDev/QuantitativeTrading/packages/execution/bingx_client.py) 內建動態時間校準。每次收到交易所回應時，自動比對交易所時間戳與本地時間差，若有微小偏離自動進行毫秒級自適應補償，永不因時鐘偏差被交易所拒絕。
3. **容器內時區貫穿 (Timezone Propagation)**：
   * Docker 容器全數掛載主機 `/etc/localtime` 與 `/etc/timezone`，並固定環境變數 `TZ=Asia/Taipei`，確保早上 08:00 與晚上 18:00 定時日報分秒不差準時發布。

### 二、伺服器雲端資安防禦（全黑洞式防護）
1. **零公網暴露 (Zero Ingress Attack Surface)**：
   * 量化操盤機器人是主動向交易所（REST/WebSocket）與 AI 伺服器發起連線，**伺服器本機完全不需要開啟任何對外監聽 Port**。
   * 防火牆預設規則為 `default deny incoming`，外界黑客掃描該 VPS 只會看到所有 Port 全部關閉，如同黑洞。
2. **Fail2ban 防爆破阻擋**：
   * 自動監控 SSH 嘗試，惡意 IP 只要密碼錯誤累積 5 次，系統自動利用 iptables 將該 IP 封鎖 1 小時。
3. **日誌防撐爆輪轉 (Log Rotation)**：
   * Docker 配置 `max-size: "10m"` 與 `max-file: "3"`，機器人日誌自動切片壓縮輪轉，永遠不會因為數個月的日誌累積而撐爆雲端硬碟。
4. **資源硬限制 (OOM Shield)**：
   * 每個機器人容器配置 `memory: 512M` 限制，防止意外記憶體洩漏造成整台 VPS 死當。
5. **金鑰實體權限隔離**：
   * `.env` 被設定為 `chmod 600`，僅限建立者帳號讀取，同主機其他進程無法旁路窺探。

---

## 5. 日常維護常用指令

| 需求 | 指令 |
| :--- | :--- |
| **查看所有機器人運行狀態** | `docker compose ps` |
| **即時查看操盤日誌 (即時滾動)** | `docker compose logs -f` |
| **單獨查看 50x 高頻機器人日誌** | `docker compose logs -f swap_50x` |
| **暫停所有操盤進程** | `docker compose stop` |
| **重啟所有操盤進程** | `docker compose restart` |
| **更新程式碼並熱重啟** | `git pull && docker compose up -d --build` |

---

## 6. 無 Docker 輕量化方案 (Linux systemd 原生守護)

若 VPS 記憶體極小（如僅 512MB~1GB），可直接使用 Linux 系統原生 `systemd` 守護服務：

```bash
# 1. 建立虛擬環境與安裝依賴
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.cargo/env
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .

# 2. 複製 systemd 設定檔
sudo cp deploy/quant-swap@.service /etc/systemd/system/
sudo cp deploy/quant-reporter.service /etc/systemd/system/
sudo systemctl daemon-reload

# 3. 啟動並設定開機自啟動
sudo systemctl enable --now quant-swap@3
sudo systemctl enable --now quant-swap@10
sudo systemctl enable --now quant-swap@50
sudo systemctl enable --now quant-reporter

# 查看狀態
sudo systemctl status quant-swap@50
```
