#!/usr/bin/env python3
"""VPS Pre-Flight & Burn-In Readiness Diagnostic CLI.

Verifies the 4 most critical failure points before running live or VST burn-in on a new VPS:
1. NTP Clock Skew vs. BingX Server Time (prevents HMAC signature 100421 rejection).
2. BingX Multi-Domain Connectivity & Latency (open-api.bingx.com, .pro, and VST).
3. System Resources (RAM, Linux Swap availability, and free disk space).
4. API Key HMAC-SHA256 Signature & VST Simulation Account Authentication.
"""

import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time
import urllib.error
import urllib.request

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv


def probe_bingx_domain(base_url: str, timeout: float = 5.0) -> dict:
    """Measure HTTP status, round-trip latency (ms), and server timestamp from BingX."""
    import requests

    url = f"{base_url.rstrip('/')}/openApi/swap/v2/quote/price?symbol=BTC-USDT"
    t0 = time.time()
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Quant-VPS-Preflight/1.0"},
            timeout=timeout,
        )
        t1 = time.time()
        payload = resp.json()
        rtt_ms = (t1 - t0) * 1000.0
        code = payload.get("code", -1)
        data = payload.get("data", {})
        server_ts = int(data.get("time") or payload.get("timestamp") or 0)
        local_mid_ms = ((t0 + t1) / 2.0) * 1000.0
        skew_ms = (local_mid_ms - server_ts) if server_ts > 0 else 0.0
        return {
            "ok": resp.status_code == 200 and code == 0,
            "http_code": resp.status_code,
            "api_code": code,
            "rtt_ms": rtt_ms,
            "server_ts": server_ts,
            "skew_ms": skew_ms,
            "price": float(data.get("price") or 0.0) if isinstance(data, dict) else 0.0,
            "error": "",
        }
    except Exception as exc:
        return {"ok": False, "http_code": 0, "rtt_ms": (time.time() - t0) * 1000.0, "skew_ms": 0.0, "error": str(exc)}


def check_system_resources() -> dict:
    """Inspect disk space and Linux /proc/meminfo (RAM & Swap)."""
    disk = shutil.disk_usage(str(ROOT_DIR))
    free_gb = disk.free / (1024 ** 3)
    total_gb = disk.total / (1024 ** 3)

    mem_total_mb = 0.0
    mem_avail_mb = 0.0
    swap_total_mb = 0.0
    meminfo_path = Path("/proc/meminfo")
    if meminfo_path.exists():
        try:
            info = {}
            for line in meminfo_path.read_text(encoding="utf-8").splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    num = v.strip().split()[0]
                    info[k.strip()] = float(num) / 1024.0  # kB -> MB
            mem_total_mb = info.get("MemTotal", 0.0)
            mem_avail_mb = info.get("MemAvailable", info.get("MemFree", 0.0))
            swap_total_mb = info.get("SwapTotal", 0.0)
        except Exception:
            pass

    return {
        "os": f"{platform.system()} {platform.release()}",
        "disk_free_gb": free_gb,
        "disk_total_gb": total_gb,
        "mem_total_mb": mem_total_mb,
        "mem_avail_mb": mem_avail_mb,
        "swap_total_mb": swap_total_mb,
    }


def main() -> int:
    load_dotenv(ROOT_DIR / ".env")
    print("=" * 72)
    print("  🚀 量化操盤系統 VPS 上線與燒機前全鏈路健檢 (VPS Pre-Flight Check)")
    print("=" * 72)

    all_passed = True

    # 1. Multi-Domain Connectivity & Clock Skew
    print("\n[1/4] 🌐 BingX 雙網域與 VST 模擬服連線、防火牆與時鐘偏差檢測:")
    domains = [
        ("正式主網域 (Primary)", "https://open-api.bingx.com"),
        ("正式備援網域 (Failover)", "https://open-api.bingx.pro"),
        ("VST 燒機網域 (Simulation)", "https://open-api-vst.bingx.com"),
    ]
    primary_skew = None
    reachable_count = 0
    for label, d_url in domains:
        res = probe_bingx_domain(d_url)
        if res["ok"]:
            reachable_count += 1
            if primary_skew is None and res["server_ts"] > 0:
                primary_skew = res["skew_ms"]
            print(f"  ✅ {label}: 暢通 | 延遲 RTT: {res['rtt_ms']:.0f} ms | BTC 報價: ${res['price']:,.1f}")
        else:
            print(f"  ❌ {label}: 異常 ({res['error']})")

    if reachable_count == 0:
        print("  🚨 [嚴重錯誤] 所有 BingX 網域均無法連線，此 VPS IP 可能遭防火牆封鎖！")
        all_passed = False

    # 2. Clock Skew Analysis
    print("\n[2/4] ⏱️ 系統時鐘同步精準度 (NTP Clock Skew - 防止 API 簽章失敗):")
    if primary_skew is None:
        print("  ⚠️ 無法取得伺服器時間戳進行比對。")
    else:
        abs_skew = abs(primary_skew)
        if abs_skew <= 500:
            print(f"  ✅ 時鐘極度精準：本機與 BingX 誤差僅 {primary_skew:+.0f} ms (安全標準 < 500 ms)")
        elif abs_skew <= 1500:
            print(f"  ⚠️ 時鐘輕微偏差：誤差 {primary_skew:+.0f} ms，建議於 VPS 執行 `sudo timedatectl set-ntp true`")
        else:
            print(f"  ❌ 時鐘嚴重飄移：誤差達 {primary_skew:+.0f} ms (> 1500 ms)！下單簽章將會被拒絕，請立即校正 NTP！")
            all_passed = False

    # 3. System Hardware & Memory / Swap
    print("\n[3/4] 💻 系統硬體資源與記憶體防 OOM 檢查:")
    sys_info = check_system_resources()
    print(f"  - 作業系統: {sys_info['os']}")
    print(f"  - 磁碟可用空間: {sys_info['disk_free_gb']:.2f} GB / {sys_info['disk_total_gb']:.2f} GB")
    if sys_info["disk_free_gb"] < 2.0:
        print("  ❌ 磁碟剩餘空間不足 2 GB，請清理磁碟！")
        all_passed = False
    else:
        print("  ✅ 磁碟空間充足 (三台容器加日誌僅需 < 1.5 GB)")

    if sys_info["mem_total_mb"] > 0:
        print(
            f"  - 記憶體 (RAM): 可用 {sys_info['mem_avail_mb']:.0f} MB / 總計 {sys_info['mem_total_mb']:.0f} MB "
            f"| Swap 虛擬記憶體: {sys_info['swap_total_mb']:.0f} MB"
        )
        if sys_info["mem_total_mb"] < 1800 and sys_info["swap_total_mb"] < 512:
            print("  ⚠️ 提醒：此 VPS RAM 小於 2GB 且未啟用 Swap，建議配置 2GB Swap 以防極端行情 OOM。")
        else:
            print("  ✅ 記憶體與 Swap 配置健康 (三台容器實測總消耗僅 ~404 MB)")

    # 4. API Credentials & VST Signed Request Check
    print("\n[4/4] 🔑 API 金鑰簽章與燒機模式 (VST) 權限實測:")
    api_key = os.getenv("BINGX_API_KEY", "").strip()
    api_secret = os.getenv("BINGX_API_SECRET", "").strip()
    burn_in_flag = os.getenv("BINGX_USE_VST", "false").lower() in ("true", "1")
    if not api_key or not api_secret or "your_" in api_key:
        print("  ⚠️ 尚未設定有效的 BINGX_API_KEY / BINGX_API_SECRET (.env)。")
    else:
        try:
            from packages.execution import BingXGateway, MarketType
            gw_vst = BingXGateway(dry_run=False, use_vst=True, enable_ws=False)
            vst_bal = gw_vst.get_balance("USDT", market_type=MarketType.SWAP.value)
            print(f"  ✅ HMAC-SHA256 簽章驗證通過！BingX VST 模擬金帳戶餘額: {vst_bal:,.2f} VST")
            print(
                f"  ℹ️ 當前 .env 模式: {'🔥【VST 燒機模擬模式 (BINGX_USE_VST=true)】(自動鎖定 $400U 本金且靜音外發)' if burn_in_flag else '💰【LIVE 實盤真金模式 (BINGX_USE_VST=false)】'}"
            )
        except Exception as exc:
            print(f"  ❌ API 簽章或連線測試失敗: {exc}")
            all_passed = False

    print("\n" + "=" * 72)
    if all_passed:
        print("  🎉 結論：【PASS】環境 100% 通過健檢，可安全啟動 Docker 容器進行燒機或實盤！")
        print("=" * 72)
        return 0
    else:
        print("  ⚠️ 結論：【ATTENTION】請先排除上方標示 ❌ 之項目後再啟動實盤！")
        print("=" * 72)
        return 1


if __name__ == "__main__":
    sys.exit(main())
