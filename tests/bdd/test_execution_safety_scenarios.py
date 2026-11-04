"""BDD Scenario Implementation Tests: execution_safety_and_precision.feature."""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
import requests
from urllib3.exceptions import NewConnectionError

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.core.autopilot_engine import UnifiedAutopilotEngine, sync_breakeven_stop_loss
from packages.execution import BingXAmbiguousRequestError, BingXClient, BingXGateway
from packages.execution.precision import round_price
from packages.journal import TradeJournalManager


class _StubAI:
    def evaluate_signal_choice(self, *args, **kwargs) -> Dict[str, Any]:
        return {"choice": "EXECUTE", "reason": "stub"}

    def summarize_trade_journal(self, raw_record: Dict[str, Any]) -> Dict[str, Any]:
        return {}


def _bullish_signals(price: float) -> Dict[str, Any]:
    """Signals that satisfy both the spot and swap trend-pullback entry rules."""
    return {
        "price": price, "rsi": 50.0, "ema21": price * 0.999, "ema50": price * 0.995, "atr": price * 0.01,
        "prev_close": price * 0.998, "in_bull_golden_pocket": False, "in_bear_golden_pocket": False,
    }


def _engine(tmp_path: Path, leverage: int, gateway: Any) -> UnifiedAutopilotEngine:
    return UnifiedAutopilotEngine(
        symbol="BTC/USDT", leverage=leverage, capital=100.0, enable_ai_veto=False, dry_run=True,
        state_file=tmp_path / "autopilot_state.json",
        journal_mgr=TradeJournalManager(db_path=str(tmp_path / "db.json"), journals_dir=str(tmp_path / "journals")),
        gateway=gateway, ai_agent=_StubAI(),
    )


def _mock_response(payload: Dict[str, Any]) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


class TestExecutionSafetyBDDScenarios:
    """BDD Step implementations matching execution_safety_and_precision.feature."""

    def test_scenario_spot_mode_entry_and_stop_do_not_crash(self, tmp_path, monkeypatch):
        """Scenario: 現貨模式 (槓桿 1) 進場與停損平倉不崩潰."""
        gw = BingXGateway(dry_run=True, default_market_type="SPOT", enable_ws=False)
        engine = _engine(tmp_path, leverage=1, gateway=gw)
        assert engine.mode == "SPOT"
        engine.arm()
        monkeypatch.setattr(engine, "_compute_market_signals", _bullish_signals)

        # When 出現現貨進場信號且引擎以 position_side=None 送出市價買單
        res = engine.step(override_price=100000.0)
        # Then 網關應正常成交而不拋出 AttributeError
        assert res["action_taken"] == "OPEN_POSITION"
        assert engine.position["side"] == "LONG"
        assert gw.get_balance("BTC", market_type="SPOT") > 0

        # And 價格跌破現貨停損 (-2%) 時應成功市價賣出平倉
        res = engine.step(override_price=97500.0)
        assert res["action_taken"] == "STOP_LOSS"
        assert engine.position["side"] == "NONE"
        assert gw.get_balance("BTC", market_type="SPOT") == pytest.approx(0.0, abs=1e-12)

    @pytest.mark.parametrize("ticker_behaviour", ["zero", "raises"])
    def test_scenario_zero_or_missing_price_never_triggers_stop(self, tmp_path, monkeypatch, ticker_behaviour):
        """Scenario: 行情報價為 0 或取得失敗時不得當作真實價格觸發停損."""
        gw = BingXGateway(dry_run=True, default_market_type="SWAP", enable_ws=False)
        engine = _engine(tmp_path, leverage=3, gateway=gw)
        engine.arm()
        engine.position = {
            "side": "LONG", "amount_btc": 0.0015, "entry_price": 100000.0, "margin_used": 50.0,
            "highest_pnl_pct": 1.0, "journal_id": "",
        }
        engine.cash = 50.0

        # When 所有行情來源失敗使網關回報價格 0 或拋出例外
        if ticker_behaviour == "zero":
            monkeypatch.setattr(gw, "fetch_ticker", lambda *a, **k: {"price": 0.0, "bid": 0.0, "ask": 0.0})
        else:
            def _boom(*a, **k):
                raise RuntimeError("All BingX domains failed")
            monkeypatch.setattr(gw, "fetch_ticker", _boom)
        create_order = MagicMock()
        monkeypatch.setattr(gw, "create_order", create_order)

        res = engine.step()

        # Then 引擎本次心跳回報 "PRICE_UNAVAILABLE"，不送單、不污染最高浮盈、持倉不變
        assert res["action_taken"] == "PRICE_UNAVAILABLE"
        create_order.assert_not_called()
        assert engine.position["side"] == "LONG"
        assert engine.position["highest_pnl_pct"] == 1.0

    def test_scenario_order_post_timeout_is_not_resent_to_fallback(self):
        """Scenario: 下單 POST 逾時不得重送至備援網域."""
        client = BingXClient(api_key="mock_key", api_secret="mock_secret")
        urls: List[str] = []

        # Given 主網域下單請求發生讀取逾時
        def _read_timeout(url, **kwargs):
            urls.append(url)
            raise requests.exceptions.ReadTimeout("read timed out")

        with patch.object(client.session, "post", side_effect=_read_timeout):
            # Then 應拋出 BingXAmbiguousRequestError 且備援網域不得再次收到下單
            with pytest.raises(BingXAmbiguousRequestError):
                client.create_swap_order("BTC-USDT", "BUY", "LONG", "MARKET", 0.001)
        assert len(urls) == 1 and "open-api.bingx.com" in urls[0]

        # And 確定未送出的連線逾時仍可安全切換至備援網域
        urls.clear()

        def _connect_fail_then_ok(url, **kwargs):
            urls.append(url)
            if "open-api.bingx.com" in url:
                raise requests.exceptions.ConnectTimeout("connect timed out")
            return _mock_response({"code": 0, "data": {"order": {"orderId": "1"}}})

        with patch.object(client.session, "post", side_effect=_connect_fail_then_ok):
            assert client.create_swap_order("BTC-USDT", "BUY", "LONG", "MARKET", 0.001)["code"] == 0
        assert len(urls) == 2 and "open-api.bingx.pro" in urls[1]

        # Refused / DNS failures (NewConnectionError) are also provably unsent.
        urls.clear()
        refused = requests.exceptions.ConnectionError(
            MagicMock(reason=NewConnectionError(None, "Connection refused"))
        )

        def _refused_then_ok(url, **kwargs):
            urls.append(url)
            if "open-api.bingx.com" in url:
                raise refused
            return _mock_response({"code": 0, "data": {"orderId": "2"}})

        with patch.object(client.session, "post", side_effect=_refused_then_ok):
            assert client.create_swap_order("BTC-USDT", "BUY", "LONG", "MARKET", 0.001)["code"] == 0
        assert len(urls) == 2

        # And GET 行情查詢維持原有雙網域容災
        def _get_read_timeout_then_ok(url, **kwargs):
            if "open-api.bingx.com" in url:
                raise requests.exceptions.ReadTimeout("read timed out")
            return _mock_response({"code": 0, "data": {"price": "1"}})

        with patch.object(client.session, "get", side_effect=_get_read_timeout_then_ok):
            assert client.fetch_ticker_price("BTC-USDT")["code"] == 0

    def test_scenario_entry_order_carries_unique_client_order_id(self, tmp_path, monkeypatch):
        """Scenario: 開倉市價單附帶唯一 clientOrderId."""
        ids: List[str] = []
        for run in range(2):
            run_dir = tmp_path / f"run{run}"
            run_dir.mkdir()
            gw = BingXGateway(dry_run=True, default_market_type="SWAP", enable_ws=False)
            engine = _engine(run_dir, leverage=3, gateway=gw)
            engine.arm()
            monkeypatch.setattr(engine, "_compute_market_signals", _bullish_signals)
            real_create = gw.create_order
            captured: Dict[str, Any] = {}

            def _capture(*args, _real=real_create, _captured=captured, **kwargs):
                _captured.update(kwargs)
                return _real(*args, **kwargs)

            monkeypatch.setattr(gw, "create_order", _capture)
            # When 引擎送出開倉市價單
            assert engine.step(override_price=100000.0)["action_taken"] == "OPEN_POSITION"
            ids.append(captured["client_order_id"])

        # Then 訂單需附帶 1~40 字元且每次唯一的 clientOrderId
        assert all(i.startswith("auto-open-") and 1 <= len(i) <= 40 for i in ids)
        assert ids[0] != ids[1]

    def test_scenario_low_price_symbol_uses_exchange_precision(self):
        """Scenario: 低價幣停損價依交易所精度取整而非固定兩位小數."""
        gw = BingXGateway(api_key="k", api_secret="s", dry_run=False, default_market_type="SWAP", enable_ws=False)
        assert gw.is_dry_run is False
        contracts = {"code": 0, "data": [{"symbol": "DOGE-USDT", "pricePrecision": 5, "quantityPrecision": 0}]}

        # Given 交易所合約規格為 DOGE-USDT pricePrecision=5、quantityPrecision=0
        with patch.object(gw.client, "fetch_swap_contracts", return_value=contracts), \
             patch.object(gw.client, "request", return_value={"code": 0, "data": {"order": {"orderId": "9"}}}) as req:
            # When 以停損價 0.1477512 與數量 1234.9 送出合約開倉單
            res = gw.create_order(
                symbol="DOGE/USDT", side="BUY", order_type="MARKET", size=1234.9,
                market_type="SWAP", position_side="LONG", leverage=3, stop_loss_price=0.1477512,
            )
        assert res["result"] is True
        params = req.call_args.kwargs["params"]
        # Then 停損價應為 0.14775 且數量向下取整為 1234
        assert json.loads(params["stopLoss"])["stopPrice"] == pytest.approx(0.14775)
        assert params["quantity"] == 1234

        # And 無法取得交易所精度時以 6 位有效數字取整，BTC 價位仍為兩位小數
        assert round_price(0.1477512) == pytest.approx(0.147751)
        assert round_price(98523.4567) == pytest.approx(98523.46)
        assert round(0.1477512, 2) == 0.15  # the old behaviour that put the stop on the entry price

    def test_scenario_failed_breakeven_sync_is_not_marked_synced(self, tmp_path):
        """Scenario: 雲端保本停損同步失敗時不得標記為已同步."""
        jm = TradeJournalManager(db_path=str(tmp_path / "db.json"), journals_dir=str(tmp_path / "journals"))
        entry = jm.on_trade_open(symbol="BTC/USDT", market_type="SWAP", side="LONG", entry_price=76000.0,
                                 amount_btc=0.0065, margin_used=50.0, leverage=10, raw_reason="BDD 保本",
                                 stop_loss_pct=15.0)
        original_stop = jm.get_entry(entry.journal_id).risk_plan.stop_loss_price
        pos = {"side": "LONG", "entry_price": 76000.0, "amount_btc": 0.0065, "journal_id": entry.journal_id}

        # Given 持倉浮盈突破半程保本門檻；When 交易所拒絕新的保本 STOP_MARKET 掛單
        gw = MagicMock(spec=["update_stop_loss_order", "round_price"])
        gw.round_price.side_effect = lambda symbol, price, market_type=None: round(price, 2)
        gw.update_stop_loss_order.return_value = {"result": False, "msg": "insufficient margin"}
        kwargs = dict(cur_price=77000.0, peak_pct=14.5, tp_threshold=20.0, leverage=10,
                      symbol="BTC/USDT", market_type="SWAP", gw=gw, journal_mgr=jm)
        assert sync_breakeven_stop_loss(pos=pos, **kwargs) is None

        # Then breakeven_synced 維持 False、日誌停損價不變並於冷卻後重試
        assert not pos.get("breakeven_synced")
        assert "insufficient margin" in pos["breakeven_sync_error"]
        assert jm.get_entry(entry.journal_id).risk_plan.stop_loss_price == original_stop
        assert sync_breakeven_stop_loss(pos=pos, **kwargs) is None
        assert gw.update_stop_loss_order.call_count == 1  # still cooling down, exchange not hammered

        # And 重試成功後才標記為已同步
        pos["breakeven_sync_retry_after"] = 0.0
        gw.update_stop_loss_order.return_value = {"result": True, "data": {"orderId": "BE-1"}}
        be_price = sync_breakeven_stop_loss(pos=pos, **kwargs)
        assert be_price is not None and be_price > 76000.0
        assert pos["breakeven_synced"] is True
        assert pos["sl_order_id"] == "BE-1"
        assert jm.get_entry(entry.journal_id).risk_plan.stop_loss_price == pytest.approx(be_price)

    def test_scenario_breakeven_replacement_places_new_stop_before_cancelling_old(self):
        """Scenario: 保本換單先掛新停損單成功後才撤銷舊停損單."""
        gw = BingXGateway(api_key="k", api_secret="s", dry_run=False, default_market_type="SWAP", enable_ws=False)
        calls: List[str] = []
        gw._precision_cache[("BTC-USDT", "SWAP")] = (1, 4)

        def _cancel(*args, **kwargs):
            calls.append("cancel")
            return {"code": 0}

        # When 新停損單掛單失敗
        def _create_fail(*args, **kwargs):
            calls.append("create")
            raise RuntimeError("BingX API Error 101204: insufficient margin")

        with patch.object(gw.client, "cancel_swap_order", side_effect=_cancel), \
             patch.object(gw.client, "create_swap_stop_order", side_effect=_create_fail):
            res = gw.update_stop_loss_order("BTC/USDT", "LONG", 76114.0, 0.0065, old_sl_order_id="OLD-1")
        # Then 舊停損單不得被撤銷
        assert res["result"] is False
        assert calls == ["create"]

        # And 新停損單掛單成功後才撤銷舊停損單
        calls.clear()

        def _create_ok(*args, **kwargs):
            calls.append("create")
            return {"code": 0, "data": {"order": {"orderId": "NEW-1"}}}

        with patch.object(gw.client, "cancel_swap_order", side_effect=_cancel), \
             patch.object(gw.client, "create_swap_stop_order", side_effect=_create_ok):
            res = gw.update_stop_loss_order("BTC/USDT", "LONG", 76114.0, 0.0065, old_sl_order_id="OLD-1")
        assert res["result"] is True
        assert calls == ["create", "cancel"]

    def test_scenario_nested_order_and_precision_fill_confirmation(self, tmp_path):
        """Scenario: 交易所回傳巢狀 order 物件或因精度取整數量時正確確認成交."""
        gw = MagicMock()
        engine = _engine(tmp_path, leverage=3, gateway=gw)

        # 1. Direct _confirm_market_fill on nested response with stepSize truncation
        nested_order_response = {
            "code": 0,
            "msg": "",
            "result": True,
            "data": {
                "order": {
                    "orderId": 2117952982117203968,
                    "symbol": "BTC-USDT",
                    "positionSide": "LONG",
                    "side": "BUY",
                    "type": "MARKET",
                    "status": "FILLED",
                    "avgPrice": "78105.5",
                    "executedQty": "0.0028",
                    "origQty": "0.0028",
                }
            },
        }

        # Requested 0.0028807, executed 0.0028 -> should be confirmed as FILLED, not PENDING!
        filled, fill_qty, fill_price, resolution = engine._confirm_market_fill(
            nested_order_response, requested_qty=0.0028807, market_type="SWAP"
        )
        assert filled is True
        assert fill_qty == pytest.approx(0.0028)
        assert fill_price == pytest.approx(78105.5)
        assert resolution == "FILLED"

        # 2. Resolution of a pending order via get_order returning nested order structure
        engine.pending_order = {
            "action": "OPEN",
            "order_id": "2117952982117203968",
            "client_order_id": "auto-open-12345",
            "candidate_signal": "LONG",
            "candidate_reason": "回踩確認",
            "ai_decision_text": "Ollama EXECUTE",
            "quantity": 0.0028807,
            "margin": 75.0,
            "price": 78105.0,
            "native_sl_price": 76933.0,
            "signals": {},
        }

        gw.get_order.return_value = {
            "code": 0,
            "msg": "",
            "result": True,
            "data": {
                "order": {
                    "orderId": 2117952982117203968,
                    "symbol": "BTC-USDT",
                    "status": "FILLED",
                    "avgPrice": "78105.5",
                    "executedQty": "0.0028",
                }
            },
        }

        resolved = engine._resolve_pending_order()
        assert resolved is True
        assert engine.pending_order is None
        assert engine.position["side"] == "LONG"
        assert engine.position["amount_btc"] == pytest.approx(0.0028)
        assert engine.position["entry_price"] == pytest.approx(78105.5)
