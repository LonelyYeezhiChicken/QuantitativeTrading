"""Quantitative Trade Review and Pedagogical Analysis Engine."""

from typing import Tuple
from packages.journal.models import TradeJournalEntry, ReviewNote, MarketSnapshot, TradeTrajectory


class JournalAnalyzer:
    """Generates structured educational reflections and quantitative takeaways for trades."""

    @staticmethod
    def generate_entry_thesis(snapshot: MarketSnapshot, side: str, market_type: str, raw_reason: str) -> str:
        """Synthesize educational pre-trade thesis based on technical indicators."""
        rsi = snapshot.rsi
        bias = snapshot.bias_pct
        price = snapshot.price
        ema = snapshot.ema21

        thesis_parts = []
        if side == "LONG":
            if rsi <= 35:
                thesis_parts.append(f"短線 RSI 達 {rsi:.1f}，進入超賣極值區，具備高性價比的均值回歸反彈條件。")
            elif 50 <= rsi <= 65:
                thesis_parts.append(f"RSI 處於 {rsi:.1f} 動能健康區間，且市價 (${price:,.2f}) 穩定收在 EMA21 (${ema:,.2f}) 之上 (乖離率 {bias:+.2f}%)，顯示多頭動能延續。")
            else:
                thesis_parts.append(f"價格呈現順勢多頭排列，技術面維持支撐，配合策略信號觸發進場。")
        else:  # SHORT
            if rsi >= 65:
                thesis_parts.append(f"短線 RSI 達 {rsi:.1f}，進入超買警戒區，短線多頭動能消耗殆盡，具備做空回調之統計優勢。")
            elif 35 <= rsi <= 50:
                thesis_parts.append(f"市價 (${price:,.2f}) 跌破 EMA21 (${ema:,.2f}) (乖離率 {bias:+.2f}%)，且 RSI 偏弱，顯示空方趨勢加劇。")
            else:
                thesis_parts.append(f"價格呈現空頭防守態勢，策略偵測到下行破位信號。")

        if raw_reason:
            thesis_parts.append(f"【系統觸發信號】：{raw_reason}")

        thesis_parts.append(f"【交易架構】：{market_type} 市場，採取嚴格預設止損保護，依據 ATR 波動度 (${snapshot.atr:,.2f}) 預留正常價格呼吸空間。")
        return "\n".join(thesis_parts)

    @staticmethod
    def analyze_exit_and_review(entry: TradeJournalEntry, exit_price: float, exit_reason: str) -> Tuple[ReviewNote, float]:
        """Compute post-trade statistics and generate in-depth pedagogical takeaways."""
        side = entry.side
        entry_p = entry.entry_price
        margin = entry.margin_used
        qty = entry.amount_btc
        leverage = entry.leverage

        # PnL Calculation
        if side == "LONG":
            pnl_usdt = (exit_price - entry_p) * qty
        else:
            pnl_usdt = (entry_p - exit_price) * qty
        pnl_pct = (pnl_usdt / margin) * 100 if margin > 0 else 0.0

        # R-Multiple
        max_risk = entry.risk_plan.max_loss_usdt
        if max_risk > 0:
            r_multiple = pnl_usdt / max_risk
        else:
            r_multiple = 1.0 if pnl_usdt >= 0 else -1.0

        # MFE / MAE analysis
        traj = entry.trajectory
        mfe = traj.mfe_pct
        mae = traj.mae_pct

        # Quality scoring (1 to 5)
        score = 3
        if pnl_pct > 0:
            if r_multiple >= 2.0:
                score = 5
            elif r_multiple >= 1.0:
                score = 4
            else:
                score = 3
        else:
            if abs(mae) <= abs(entry.risk_plan.stop_loss_pct) * 1.1:
                score = 3  # Disciplined stop loss
            else:
                score = 2

        # 1. Exit reason synthesis
        exit_synthesis = []
        exit_synthesis.append(f"- 出場執行點：`${exit_price:,.2f}` (相較進場均價 `${entry_p:,.2f}`)。")
        exit_synthesis.append(f"- 觸發機制：{exit_reason}。")
        if "追蹤止盈" in exit_reason or "TRAILING" in exit_reason.upper():
            exit_synthesis.append(f"- 利潤保護分析：盤中最高浮盈曾達 `+{mfe:.2f}%`，自波段高點回撤觸發動態出場，成功將浮盈轉化為實現利潤。")
        elif "止損" in exit_reason or "STOP" in exit_reason.upper():
            exit_synthesis.append(f"- 停損紀律分析：行情未符預期假說，觸發硬止損保護，有效避免後續潛在更大單邊風險。")
        else:
            exit_synthesis.append(f"- 信號反轉或手動平倉退出，結算總盈虧 `${pnl_usdt:+,.2f} USDT`。")

        # 2. Strategy evaluation
        eval_parts = []
        eval_parts.append(f"- **風險控制執行**：預期最大承受風險 `${max_risk:.2f} USDT`，實際實現盈虧 `${pnl_usdt:+,.2f} USDT` (實際 R 倍數: `{r_multiple:+.2f}R`)。")
        eval_parts.append(f"- **部位耐受性 (MAE/MFE)**：持倉期間最大不利回撤為 `{mae:.2f}%`，最大有利獲利為 `+{mfe:.2f}%`。")
        if pnl_pct > 0 and mfe > pnl_pct * 1.5:
            eval_parts.append("- **獲利鎖定優化建議**：盤中獲利曾顯著高於最終平倉獲利，未來可考慮分批停利 (Partial TP) 策略以進一步提高獲利勝率。")
        elif pnl_pct > 0:
            eval_parts.append("- **執行效率優秀**：獲利離場點位與盤中最高點貼近，動態停利回撤參數設定得宜。")
        else:
            eval_parts.append("- **停損保護驗證**：嚴格執行既定風控計畫，不抱持僥倖扛單心理，符合正期望值交易原則。")

        # 3. Pedagogical Takeaways for Human Trader Learning
        takeaways = []
        if pnl_pct > 0:
            takeaways.append("1. **【順勢與時機】**：本筆交易在指標未過度超買前確認趨勢進場，驗證了「順應主要均線方向、不預測逆勢摸頂摸底」的勝率優勢。")
            takeaways.append("2. **【鎖定利潤與回撤容忍】**：在真實人工交易中，面對浮盈時常有「過早平倉怕獲利溜走」或「捨不得走結果抱上去又抱下來」的心理。量化追蹤停利透過明確的回撤趴數（例如 1.2%）解決了這個人性弱點。")
            takeaways.append("3. **【複利累積要訣】**：獲利的關鍵不在於單筆暴利，而是每一筆正 R 值的穩定積累。保持這類高盈虧比機會的執行一致性。")
        else:
            takeaways.append("1. **【停損是做生意的必要成本】**：金融交易沒有百分之百勝率。嚴格接受一筆小虧損，是為了保留本金參與下一筆具備統計優勢的交易。")
            takeaways.append("2. **【避免凹單與報復性交易】**：量化系統在止損觸發後即刻冷靜進入觀望，絕不情緒化立即追空或反向重倉。這是一般人工主觀交易者最常虧損的盲點，值得深切借鑑。")
            takeaways.append("3. **【進場過濾機制精進】**：可檢視進場當下的成交量能是否背離，未來可加入多週期共振確認以進一步提升過濾假突破之能力。")

        review = ReviewNote(
            thesis=entry.review.thesis,
            exit_reason="\n".join(exit_synthesis),
            strategy_evaluation="\n".join(eval_parts),
            pedagogical_takeaway="\n".join(takeaways),
            quality_score=score,
        )
        return review, r_multiple
