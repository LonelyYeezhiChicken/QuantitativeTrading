# Graph Report - QuantitativeTrading  (2026-11-04)

## Corpus Check
- 188 files · ~180,791 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 42 file(s) not represented in the graph (top: .parquet 19, .feature 17, (none) 2)

## Summary
- 2543 nodes · 4309 edges · 178 communities (142 shown, 36 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 364 edges (avg confidence: 0.87)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `3eb18f14`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- json
- BollingerBreakoutModel
- BingXClient
- scoring.py
- Agent Interaction Rules
- BingX Swap WebSocket Account Data — API Reference
- review.py
- BingX Coin-M WebSocket Account Data — API Reference
- execution/__init__.py
- BingXWebSocketClient
- BingX Agent — API Reference
- BingX Copy Trade USDT-M Perpetual Contracts — API Reference
- BingX Spot Wallet — API Reference
- BingXGateway
- BingX Swap Market Data — API Reference
- PionexClient
- BingX Fund Account — API Reference
- BingX Spot WebSocket Account Data
- StrategyConvergenceAnalyzer
- BingX Coin-M (CSwap) Market Data — API Reference
- Account and Assets
- BingX Spot Market Data — API Reference
- BingX Copy Trade Spot — API Reference
- PaperBroker
- dashboard/app.py
- TypeSafeAIAgent
- UnifiedAutopilotEngine
- test
- 交易學習日誌：SPOT_20261103_124013_LONG
- BingX Swap Account — API Reference
- overnight_trading_bot.py
- BingX Standard Contract Trading
- LGBMAgent
- BingX Maker Entry
- BingX RSI Bottom Hunter
- BingX Announcement API
- BingX Technical Analysis
- .evaluate_signal_choice
- BingX Dynamic SL/TP
- BingX Trade Review
- 加密貨幣 AI 多因子量化交易平台 (Crypto AI Quant Trading Platform)
- Execution Steps
- tags.py
- PionexGateway
- BingX Coin-M (CSwap) Trade — API Reference
- 78 Indicator Quick Reference
- BingX Trading Plan
- .on_trade_open
- render_research_tab
- 3.1 保留並納入主力實盤 (KEEP - Core Production)
- pipeline.py
- overview_tab.py
- json
- BingX Swap Trade
- Agent Interaction Rules
- TradeJournalEntry
- Default Parameters & Tuning Guide
- 交易學習日誌：SPOT_20261104_030323_LONG
- 系統工程架構與協作交接手冊 (Engineering Handover & Architecture Specification)
- Agent Interaction Rules
- Sentiment Calculation Reference
- params
- SL/TP Strategy Reference
- BingX Swap WebSocket Market Data
- Maker vs Taker Fee Comparison
- pandas
- BingX Perpetual Swap Trade — API Reference
- BingX Trading Plan API Reference
- Any
- render_research_tab
- BingX Sub-Account Management — API Reference
- 4. Transfers & Deposits
- IX. Additional Endpoints
- config.yaml
- BingX Coin-M (CSwap) Trade
- BingX Coin-M WebSocket Market Data
- BingX Coin-M WebSocket Market Data — API Reference
- 交易學習日誌：SWAP_20261104_021759_LONG
- BingX Spot WebSocket Market Data
- BingX Spot WebSocket Market Data — API Reference
- BingX Sub-Account Management
- Incremental Depth Information
- features
- 交易學習日誌：SWAP_20261104_041621_SHORT
- Agent Interaction Rules
- III. Order Queries
- V. Leverage and Mode Settings
- Subscribe Market Depth Data
- API Endpoints
- model
- exchange
- main
- CustomDummyMomentumModel
- Parameters
- Subscription: Limited Depth
- Subscription: K-Line Data
- CCXTFetcher
- Subscription: Market Depth
- Subscription: Incremental and Full Depth
- Subscription: K-Line Streams
- 2. Sub-account Lifecycle
- Parameters
- VII. TWAP Orders
- Subscribe K-Line Data
- Subscribe the Latest Trade Detail
- backtest
- journal/__init__.py
- test_pionex_gateway.py
- Subscription: Trade Detail
- Subscription: Best Bid and Ask (Book Ticker)
- Subscription: Latest Trade Price
- Subscription: Mark Price
- Subscription: Trade Detail
- Subscription: 24-Hour Price Change
- Subscription: Latest Trade Price
- Agent Interaction Rules
- 1. Account Identity
- Appendix: Enum Reference
- VIII. Multi-Assets Mode
- II. Cancel Orders
- BingX Swap WebSocket Market Data — API Reference
- Subscribe to 24-Hour Price Changes
- Subscribe to Latest Price Changes
- Subscribe to Latest Mark Price Changes
- Subscribe to Book Ticker Streams
- data
- Agent Interaction Rules
- Parameters
- Parameters
- IV. Position Management
- Parameters
- TestAutonomousOrchestrationBDDScenarios
- sys
- test_pionex_scenarios.py
- test_bingx.py
- 11. Set Leverage
- 12. Query Margin Type
- 13. Set Margin Type
- 14. Adjust Position Margin
- 1. Place Order
- 3. Cancel All Open Orders
- 6. Query Order Detail
- 7. Query Order History
- 9. Query Liquidation Orders
- 交易學習日誌：SWAP_20261103_140101_LONG
- crypto-ai-quant
- test_bingx_gateway.py
- 交易學習日誌：SWAP_20261104_021851_LONG
- 交易學習日誌：SWAP_20261104_015145_SHORT
- overnight_swap_bot.py
- 交易學習日誌：SWAP_20261104_002045_SHORT
- 交易學習日誌：SWAP_20261104_022601_LONG
- 交易學習日誌：SWAP_20261104_023102_LONG
- 交易學習日誌：SWAP_20261104_030108_LONG
- INDEX.md
- 交易學習日誌：SWAP_20261104_030257_LONG
- 交易學習日誌：SWAP_20261104_031009_LONG
- 交易學習日誌：SWAP_20261104_033213_LONG
- cli/interactive_menu.py
- calculator.py
- sentiment.py
- .test_scenario_gateway_hybrid_prioritization_and_fallback
- analyze.py
- ahr999.py
- streamlit
- argparse
- TestNativeStopLossAndDisconnectionBDDScenarios

## God Nodes (most connected - your core abstractions)
1. `BingXGateway` - 75 edges
2. `TradeJournalManager` - 61 edges
3. `UnifiedAutopilotEngine` - 56 edges
4. `BingXClient` - 42 edges
5. `PaperBroker` - 41 edges
6. `BaseTradingModel` - 38 edges
7. `LGBMAgent` - 32 edges
8. `render_research_tab()` - 29 edges
9. `StrategyConvergenceAnalyzer` - 29 edges
10. `CCXTFetcher` - 28 edges

## Surprising Connections (you probably didn't know these)
- `5. BDD 規格驅動測試矩陣 (BDD Test Matrix)` --references--> `TradeJournalManager`  [INFERRED]
  AGENTS.md → packages/journal/manager.py
- `1. 系統設計哲學 (Design Principles)` --references--> `BaseTradingModel`  [INFERRED]
  AGENTS.md → packages/models/base.py
- `1. 系統設計哲學 (Design Principles)` --references--> `BaseBrokerGateway`  [INFERRED]
  AGENTS.md → packages/execution/base.py
- `print_status()` --uses--> `AutopilotState`  [INFERRED]
  apps/cli/autopilot.py → packages/core/autopilot_engine.py
- `main()` --uses--> `AutopilotState`  [INFERRED]
  apps/cli/autopilot.py → packages/core/autopilot_engine.py

## Import Cycles
- None detected.

## Communities (178 total, 36 thin omitted)

### Community 0 - "json"
Cohesion: 0.18
Nodes (5): build_confirmation(), main(), ta_checks(), main(), score_single()

### Community 3 - "scoring.py"
Cohesion: 0.30
Nodes (13): confidence(), extract_lindorm_rows(), first_number(), label(), main(), parse_lindorm_rows(), parse_row_extra(), score_funding() (+5 more)

### Community 4 - "Agent Interaction Rules"
Cohesion: 0.04
Nodes (44): BingX Spot Trade — API Reference, Cancel Order, Common Error Codes, GET /openApi/spot/v1/oco/historyOrderList — Query Historical OCO Orders, GET /openApi/spot/v1/oco/openOrderList — Query All Open OCO Orders, GET /openApi/spot/v1/oco/orderList — Query OCO Order Details, GET /openApi/spot/v1/trade/historyOrders — Query Order History, GET /openApi/spot/v1/trade/myTrades — Query Trade Fills (+36 more)

### Community 5 - "BingX Swap WebSocket Account Data — API Reference"
Cohesion: 0.05
Nodes (41): Account Balance and Position Update (ACCOUNT_UPDATE), Account Config Update (ACCOUNT_CONFIG_UPDATE), BingX Swap WebSocket Account Data — API Reference, Connection, Delete Listen Key, Error Codes, Example, Execution Types (+33 more)

### Community 6 - "review.py"
Cohesion: 0.26
Nodes (5): main(), calc_stats(), generate_charts(), main(), parse_period()

### Community 7 - "BingX Coin-M WebSocket Account Data — API Reference"
Cohesion: 0.05
Nodes (40): Account Balance and Position Update (ACCOUNT_UPDATE), Account Config Update (ACCOUNT_CONFIG_UPDATE), BingX Coin-M WebSocket Account Data — API Reference, Connection, Delete Listen Key, Error Codes, Example, Execution Types (+32 more)

### Community 8 - "execution/__init__.py"
Cohesion: 0.07
Nodes (4): 1. 系統設計哲學 (Design Principles), BaseBrokerGateway, MarketType, TestBrokerGatewayPolymorphismBDDScenarios

### Community 9 - "BingXWebSocketClient"
Cohesion: 0.06
Nodes (3): BingXWebSocketClient, test_ws_client_message_processing(), test_ws_client_xaut_processing()

### Community 10 - "BingX Agent — API Reference"
Cohesion: 0.05
Nodes (38): 1. Query Invited Users, 2. Daily Commission Details (Invitation Relationship), 3. Query Agent User Information, 4. Query API Transaction Commission (Non-Invitation Relationship), 5. Query Partner Information, 6. Query Deposit Details of Invited Users, 7. Invitation Code Data, 8. Superior Verification (+30 more)

### Community 11 - "BingX Copy Trade USDT-M Perpetual Contracts — API Reference"
Cohesion: 0.05
Nodes (35): 1. Trader's Current Orders, 2. Close Position by Order Number, 3. Set Take Profit and Stop Loss by Order Number, 4. Personal Trading Overview, 5. Profit Overview, 6. Profit Details, 7. Set Commission Rate, 8. Trader Gets Copy Trading Pairs (+27 more)

### Community 12 - "BingX Spot Wallet — API Reference"
Cohesion: 0.06
Nodes (34): 1. Deposit Records, 2. Withdrawal Records, 3. Coin Config, 4. Withdraw, 5. Deposit Address, 6. Deposit Risk Control Records, BingX Spot Wallet — API Reference, Common Error Codes (+26 more)

### Community 13 - "BingXGateway"
Cohesion: 0.08
Nodes (8): get_market_analysis(), fetch_swap_signals(), fetch_market_signals(), render_trading_tab(), BingXGateway, TestBingXVSTBDDScenarios, TestMarketTypeBDDScenarios, test_dry_run_buy_sell_and_cancel()

### Community 14 - "BingX Swap Market Data — API Reference"
Cohesion: 0.06
Nodes (33): 10. Historical Trades, 11. Mark Price Kline/Candlestick Data, 12. Symbol Price Ticker, 13. Trading Rules, 14. Get Server Time, 15. Trading Schedule, 1. Get Contract Info, 2. Order Book Depth (+25 more)

### Community 16 - "BingX Fund Account — API Reference"
Cohesion: 0.06
Nodes (31): 1. Fund Account Balance, 2. Asset Overview (All Accounts), 3. Asset Transfer, 4. Asset Transfer Records, 5. Main Account Internal Transfer, 6. Main Account Internal Transfer Records, BingX Fund Account — API Reference, Common Error Codes (+23 more)

### Community 17 - "BingX Spot WebSocket Account Data"
Cohesion: 0.06
Nodes (31): BingX Spot WebSocket Account Data — API Reference, Connection, Delete Listen Key, Error Codes, Extend Listen Key Validity, Generate Listen Key, Listen Key REST APIs, Parameters (+23 more)

### Community 18 - "StrategyConvergenceAnalyzer"
Cohesion: 0.07
Nodes (6): generate_markdown_report(), main(), StrategyConvergenceAnalyzer, StrategyEvaluationSummary, RollingBacktestEvaluator, TestStrategyConvergenceBDDScenarios

### Community 19 - "BingX Coin-M (CSwap) Market Data — API Reference"
Cohesion: 0.06
Nodes (30): 1. Contract Information, 2. Order Book Depth, 3. K-line / Candlestick Data, 4. Mark Price & Current Funding Rate, 5. Open Interest Statistics, 6. 24hr Ticker Price Change Statistics, BingX Coin-M (CSwap) Market Data — API Reference, Common Error Codes (+22 more)

### Community 20 - "Account and Assets"
Cohesion: 0.07
Nodes (28): 1. Query Spot Account Balance, 2. Query Fund Account Balance, 3. Asset Overview (All Accounts), 4. Transfer Assets Between Accounts, 5. Query Asset Transfer Records (v3), 6. Query Asset Transfer Records (new format), 7. Query Supported Coins for Transfer, 8. Internal P2P Transfer (Main Account) (+20 more)

### Community 21 - "BingX Spot Market Data — API Reference"
Cohesion: 0.07
Nodes (28): 10. Historical Trade Lookup, 1. Get Spot Trading Symbols, 2. Order Book Depth (v1), 3. Order Book Aggregation (v2), 4. Recent Trades, 5. Kline / Candlestick Data (v2), 6. 24h Ticker Price Change Statistics, 7. Symbol Price Ticker (+20 more)

### Community 22 - "BingX Copy Trade Spot — API Reference"
Cohesion: 0.07
Nodes (27): 1. Trader Sells Spot Assets, 2. Personal Trading Overview, 3. Profit Summary, 4. Profit Details, 5. Query Historical Orders, BingX Copy Trade Spot — API Reference, Common Error Codes, Personal Trading Overview (+19 more)

### Community 24 - "dashboard/app.py"
Cohesion: 0.17
Nodes (11): get_unified_journal_entries(), load_bot_states(), main(), _render_journal_live(), _render_journal_manual(), _render_overview_10s(), _render_overview_3s(), _render_overview_5s() (+3 more)

### Community 25 - "TypeSafeAIAgent"
Cohesion: 0.12
Nodes (3): main(), TypeSafeAIAgent, test_typesafe_mock_inference_scenarios()

### Community 26 - "UnifiedAutopilotEngine"
Cohesion: 0.08
Nodes (3): main(), print_status(), UnifiedAutopilotEngine

### Community 27 - "test"
Cohesion: 0.08
Nodes (25): concurrency, cancel-in-progress, group, jobs, test, os, python-version, name (+17 more)

### Community 28 - "交易學習日誌：SPOT_20261103_124013_LONG"
Cohesion: 0.18
Nodes (10): 1. 進場立論假說 (Trade Thesis), 2. 出場歸因 (Exit Catalyst), 3. 策略執行評價 (Strategy Evaluation), 4. 給操盤手的學習心得與啟發 (Pedagogical Takeaway), 一、基本交易參數, 三、前置風控計畫 (Pre-Trade Risk Management), 二、進場環境與技術面快照, 五、學習覆盤與策略反思 (Pedagogical Reflection) (+2 more)

### Community 29 - "BingX Swap Account — API Reference"
Cohesion: 0.08
Nodes (23): 1. Query Account Balance, 2. Query Position Data, 3. Query User Commission Rate, 4. Query Fund Flow (Income), 5. Export Fund Flow, BingX Swap Account — API Reference, Common Error Codes, Additional Resources (+15 more)

### Community 30 - "overnight_trading_bot.py"
Cohesion: 0.22
Nodes (7): execute_buy(), execute_sell(), handle_exit(), load_state(), log_msg(), main(), save_state()

### Community 31 - "BingX Standard Contract Trading"
Cohesion: 0.10
Nodes (19): 1. Query Positions, 2. Query Historical Orders, 3. Query Standard Contract Balance, BingX Standard Contract API Reference, Common Error Codes, 1. Query Positions, 2. Query Historical Orders, 3. Query Standard Contract Balance (+11 more)

### Community 32 - "LGBMAgent"
Cohesion: 0.12
Nodes (3): main(), PurgedTimeSeriesSplit, LGBMAgent

### Community 33 - "BingX Maker Entry"
Cohesion: 0.10
Nodes (19): Agent Interaction Rules, BingX Maker Entry, Common Calls, Completion Summary, Error Handling, Execution Steps, In Progress, Order Plan Confirmation (+11 more)

### Community 34 - "BingX RSI Bottom Hunter"
Cohesion: 0.10
Nodes (19): Agent Interaction Rules, BingX RSI Bottom Hunter, Common Calls, Error Handling, Execution Steps, Monitor Mode — On Start, Once Mode — Confirm When Condition Met, Output Templates (+11 more)

### Community 35 - "BingX Announcement API"
Cohesion: 0.11
Nodes (17): 1. Get Announcements, BingX Announcement — API Reference, contentType Enum, Error Handling, Additional Resources, Agent Interaction Rules, BingX Announcement API, Code Usage Rules (+9 more)

### Community 36 - "BingX Technical Analysis"
Cohesion: 0.11
Nodes (18): Agent Interaction Rules, BingX Technical Analysis, Common Calls, Error Handling, Execution Steps, Full Mode, Indicator Mode, Output Templates (+10 more)

### Community 38 - "BingX Dynamic SL/TP"
Cohesion: 0.11
Nodes (17): Agent Interaction Rules, BingX Dynamic SL/TP, Common Calls, Error Handling, Execution Steps, Output Templates, Quick Reference, Quick Start (+9 more)

### Community 39 - "BingX Trade Review"
Cohesion: 0.11
Nodes (17): Agent Interaction Rules, BingX Trade Review, Common Calls, Compare Mode, Error Handling, Execution Steps, Output Templates, Quick Reference (+9 more)

### Community 40 - "加密貨幣 AI 多因子量化交易平台 (Crypto AI Quant Trading Platform)"
Cohesion: 0.10
Nodes (19): 1. 現貨 (SPOT) 與 永續合約 (SWAP) 雙軌執行網關, 1. 系統依賴, 2. BingX 官方 OpenAPI 深度對接, 2. 安裝與環境同步, 3. TypeSafe AI (Jev) 短線決策引擎, 3. 配置金鑰 (選填), 4. 嚴格防範資料外洩 (Zero Data Leakage) 特徵工程, 4. 驗證與啟動 (+11 more)

### Community 41 - "Execution Steps"
Cohesion: 0.12
Nodes (16): Agent Interaction Rules, BingX Sentiment Dashboard, Common Calls, Execution Steps, Output Template, Quick Reference, Quick Start, Step 1 - Parse Intent (+8 more)

### Community 42 - "tags.py"
Cohesion: 0.25
Nodes (13): ensure_dir(), get_trade(), load(), merge_with_api(), save(), upsert_trade(), cmd_add(), cmd_batch() (+5 more)

### Community 44 - "BingX Coin-M (CSwap) Trade — API Reference"
Cohesion: 0.12
Nodes (16): 10. Query Leverage, 15. Query Commission Rate, 16. Query Account Assets, 17. Get Current Positions, 2. Cancel Order, 4. Close All Positions, 5. Query Open Orders, 8. Query Trade Fill History (+8 more)

### Community 45 - "78 Indicator Quick Reference"
Cohesion: 0.12
Nodes (15): 1. Get Klines, 2. Get Premium Index & Funding Rate, 3. Get Open Interest, 62 Candlestick Pattern Quick Reference, 78 Indicator Quick Reference, API Endpoints, Bearish Reversal Patterns, Bullish Reversal Patterns (+7 more)

### Community 46 - "BingX Trading Plan"
Cohesion: 0.12
Nodes (15): Agent Interaction Rules, BingX Trading Plan, Common Calls, Direction Rules, Execution Steps, Output Template, Quick Reference, Quick Start (+7 more)

### Community 47 - ".on_trade_open"
Cohesion: 0.09
Nodes (4): TradeJournalManager, TestTradeJournalBDDScenarios, TestMultiprocessAndLifecycleBDDScenarios, test_trade_lifecycle_in_manager()

### Community 48 - "render_research_tab"
Cohesion: 0.13
Nodes (3): get_model(), main(), RSIMomentumModel

### Community 49 - "3.1 保留並納入主力實盤 (KEEP - Core Production)"
Cohesion: 0.12
Nodes (15): 1. 五年全週期績效排行榜 (5-Year Performance Ranking Matrix), 2. 逐年市場行情適應性矩陣 (Year-by-Year Multi-Regime Breakdown), 3.1 保留並納入主力實盤 (KEEP - Core Production), 3.2 具備優勢但需優化調校 (OPTIMIZE - High Potential Refinement), 3.3 淘汰捨棄或除役 (DISCARD - Inadequate Risk/Reward), 3. 策略收斂淘汰決策剖析 (Convergence & Pruning Breakdown), 比特幣 (BTC/USDT) 五年 (2021~2025) 策略回測矩陣與收斂淘汰權威報告, 策略：`Bollinger_Breakout_20_2.0` (波動通道突破) (+7 more)

### Community 50 - "pipeline.py"
Cohesion: 0.20
Nodes (5): calculate_atr(), calculate_bollinger_bands(), calculate_macd(), calculate_returns(), calculate_rsi()

### Community 51 - "overview_tab.py"
Cohesion: 0.17
Nodes (3): discover_active_bot_instances(), load_config(), BotStateRepository

### Community 52 - "json"
Cohesion: 0.26
Nodes (8): adjust_mode(), calc_tick_size(), main(), parse_orderbook(), plan_mode(), load_state(), main(), save_state()

### Community 53 - "BingX Swap Trade"
Cohesion: 0.14
Nodes (12): Additional Resources, BingX Swap Trade, Code Usage Rules, Common Calls, Enums, Order Parameters, Parameter Validation Rules, Parameters (+4 more)

### Community 54 - "Agent Interaction Rules"
Cohesion: 0.14
Nodes (14): Agent Interaction Rules, Cancel Order Flow, Close Position Flow, Leverage Settings Flow, Margin Type Flow, Position Mode Flow, Step 1 — Identify the Operation, Step 2 — Collect symbol (if not provided) (+6 more)

### Community 55 - "TradeJournalEntry"
Cohesion: 0.17
Nodes (4): main(), print_entry_detail(), print_list_view(), TradeJournalEntry

### Community 56 - "Default Parameters & Tuning Guide"
Cohesion: 0.15
Nodes (12): 1. Get Klines, 2. Place Order, 3. Cancel Order, Aggressive (more signals), API Endpoints, Balanced (default, recommended for beginners), Conservative (high-confidence only), Default Parameters (+4 more)

### Community 57 - "交易學習日誌：SPOT_20261104_030323_LONG"
Cohesion: 0.18
Nodes (10): 1. 進場立論假說 (Trade Thesis), 2. 出場歸因 (Exit Catalyst), 3. 策略執行評價 (Strategy Evaluation), 4. 給操盤手的學習心得與啟發 (Pedagogical Takeaway), 一、基本交易參數, 三、前置風控計畫 (Pre-Trade Risk Management), 二、進場環境與技術面快照, 五、學習覆盤與策略反思 (Pedagogical Reflection) (+2 more)

### Community 58 - "系統工程架構與協作交接手冊 (Engineering Handover & Architecture Specification)"
Cohesion: 0.18
Nodes (10): 1. BingX 官方 OpenAPI 整合規範, 2. 環境變數配置規程, 2. 領域模組分層與協議契約 (Package Contracts), 3. 現貨 (SPOT) 與 永續合約 (SWAP) 雙軌執行機制, 4. 外部通訊與安全規範 (External APIs & Security), 5. BDD 規格驅動測試矩陣 (BDD Test Matrix), 6. 協作與開發常用指令 (Developer Cheat Sheet), 7. 學術免責聲明 (Academic Disclaimer) (+2 more)

### Community 59 - "Agent Interaction Rules"
Cohesion: 0.17
Nodes (12): Agent Interaction Rules, Cancel Order Flow, Leverage Settings Flow, Margin Type Flow, Step 1 — Identify the Operation, Step 2 — Collect symbol (if not provided), Step 3 — Collect side (for order placement), Step 4 — Collect positionSide (+4 more)

### Community 60 - "Sentiment Calculation Reference"
Cohesion: 0.17
Nodes (11): AHR999 Index Zones, BingX Sentiment Dashboard API Reference, Composite Score Weights, Composite Sentiment Score Levels, Fear & Greed Index, Funding Rate Signals, Funding Rates, Klines (+3 more)

### Community 61 - "params"
Cohesion: 0.17
Nodes (12): params, boosting_type, colsample_bytree, learning_rate, max_depth, metric, n_estimators, num_leaves (+4 more)

### Community 62 - "SL/TP Strategy Reference"
Cohesion: 0.18
Nodes (10): 1. Get Klines, 2. Place Conditional Order (SL/TP), 3. Cancel Conditional Order, API Endpoints, Default Partial Take-Profit Plan, Quick Selection Guide, SL/TP Strategy Reference, Stop-Loss Strategies (+2 more)

### Community 63 - "BingX Swap WebSocket Market Data"
Cohesion: 0.18
Nodes (11): Additional Resources, Agent Interaction Rules, BingX Swap WebSocket Market Data, Code Usage Rules, Common Calls, Operation Identification, Quick Reference, Quick Start (+3 more)

### Community 64 - "Maker vs Taker Fee Comparison"
Cohesion: 0.20
Nodes (9): 1. Get Order Book Depth, 2. Place Order, 3. Cancel Order, API Endpoints, BingX Perpetual Futures Fee Rates, Dynamic Adjustment Rules, Fee Savings Examples, Maker vs Taker Fee Comparison (+1 more)

### Community 65 - "pandas"
Cohesion: 0.09
Nodes (6): FibonacciSNRModel, SpotMomentumPullbackModel, SwapMultiRegimeModel, BaseTradingModel, DualEMACrossoverModel, TestStrategyContractBDDScenarios

### Community 66 - "BingX Perpetual Swap Trade — API Reference"
Cohesion: 0.20
Nodes (10): 1. Place Order, 23. Amend Order, 24. Cancel and Replace Order, 25. Batch Cancel and Replace Orders (batchCancelReplace), 2. Test Place Order, 3. Batch Place Orders, BingX Perpetual Swap Trade — API Reference, Common Error Codes (+2 more)

### Community 67 - "BingX Trading Plan API Reference"
Cohesion: 0.20
Nodes (9): BingX Trading Plan API Reference, Depth, Funding Rate, Global Account Long-Short Ratio, Internal Lindorm Query, Klines, Liquidation Heatmap, Top Account Long-Short Ratio (+1 more)

### Community 69 - "render_research_tab"
Cohesion: 0.11
Nodes (6): create_candlestick_chart(), create_equity_curve_chart(), create_feature_importance_chart(), render_research_tab(), BacktestEngine, calculate_performance_metrics()

### Community 70 - "BingX Sub-Account Management — API Reference"
Cohesion: 0.22
Nodes (9): 3.1 Create API Key for Sub-account, 3.2 Edit Sub-account API Key, 3.3 Delete Sub-account API Key, 3. API Key Management, 5.1 Query API Key Permissions, 5.2 Create Deposit Address for Sub-account, 5. Permissions & Addresses, BingX Sub-Account Management — API Reference (+1 more)

### Community 71 - "4. Transfers & Deposits"
Cohesion: 0.22
Nodes (9): 4.1 Authorize Sub-account Internal Transfers, 4.2 Sub-account Internal Transfer, 4.3 Get Sub-account Deposit Addresses, 4.4 Get Sub-account Deposit Records, 4.5 Query Sub-account Internal Transfer Records, 4.6 Query Sub-account Transfer History (Master Account Only), 4.7 Query Transferable Amounts (Master Account Only), 4.8 Sub-account Asset Transfer (Master Account Only) (+1 more)

### Community 72 - "IX. Additional Endpoints"
Cohesion: 0.22
Nodes (9): 35. All Orders (V2), 36. Query Historical Transaction Details, 37. Query Position History, 38. Isolated Margin Change History, 39. Position and Maintenance Margin Ratio, 40. Automatic Margin Addition, 41. One-Click Reverse Position, 42. Apply VST (+1 more)

### Community 74 - "config.yaml"
Cohesion: 0.22
Nodes (8): risk, atr_multiplier_stop, daily_max_drawdown_limit, max_position_size, system, project_name, random_seed, version

### Community 75 - "BingX Coin-M (CSwap) Trade"
Cohesion: 0.25
Nodes (6): Additional Resources, BingX Coin-M (CSwap) Trade, Code Usage Rules, Common Calls, Quick Reference, Quick Start

### Community 76 - "BingX Coin-M WebSocket Market Data"
Cohesion: 0.25
Nodes (6): Additional Resources, BingX Coin-M WebSocket Market Data, Code Usage Rules, Common Calls, Quick Reference, Quick Start

### Community 77 - "BingX Coin-M WebSocket Market Data — API Reference"
Cohesion: 0.25
Nodes (8): BingX Coin-M WebSocket Market Data — API Reference, Connection, dataType Format, Error Codes, Parameters, Response Fields, Subscription: 24-Hour Price Change, Subscription Request

### Community 78 - "交易學習日誌：SWAP_20261104_021759_LONG"
Cohesion: 0.18
Nodes (10): 1. 進場立論假說 (Trade Thesis), 2. 出場歸因 (Exit Catalyst), 3. 策略執行評價 (Strategy Evaluation), 4. 給操盤手的學習心得與啟發 (Pedagogical Takeaway), 一、基本交易參數, 三、前置風控計畫 (Pre-Trade Risk Management), 二、進場環境與技術面快照, 五、學習覆盤與策略反思 (Pedagogical Reflection) (+2 more)

### Community 79 - "BingX Spot WebSocket Market Data"
Cohesion: 0.25
Nodes (6): Additional Resources, BingX Spot WebSocket Market Data, Code Usage Rules, Common Calls, Quick Reference, Quick Start

### Community 80 - "BingX Spot WebSocket Market Data — API Reference"
Cohesion: 0.25
Nodes (8): BingX Spot WebSocket Market Data — API Reference, Connection, dataType Format, Error Codes, Parameters, Response Fields, Subscription: Best Order Book (Book Ticker), Subscription Request

### Community 81 - "BingX Sub-Account Management"
Cohesion: 0.25
Nodes (6): Additional Resources, BingX Sub-Account Management, Code Usage Rules, Common Calls, Quick Reference, Quick Start

### Community 82 - "Incremental Depth Information"
Cohesion: 0.25
Nodes (8): dataType Format, How to Maintain Incremental Depth Locally, Incremental Depth Information, Parameters, Response Examples, Response Fields, Subscription Request, Update ID and Recovery Limits

### Community 83 - "features"
Cohesion: 0.25
Nodes (8): features, atr_period, bollinger_period, bollinger_std, label_threshold, lookback_periods, rsi_periods, target_horizon

### Community 84 - "交易學習日誌：SWAP_20261104_041621_SHORT"
Cohesion: 0.18
Nodes (10): 1. 進場立論假說 (Trade Thesis), 2. 出場歸因 (Exit Catalyst), 3. 策略執行評價 (Strategy Evaluation), 4. 給操盤手的學習心得與啟發 (Pedagogical Takeaway), 一、基本交易參數, 三、前置風控計畫 (Pre-Trade Risk Management), 二、進場環境與技術面快照, 五、學習覆盤與策略反思 (Pedagogical Reflection) (+2 more)

### Community 85 - "Agent Interaction Rules"
Cohesion: 0.29
Nodes (7): Agent Interaction Rules, JSON Body Endpoints (Reminder), Step 1 — Identify the Operation, Step 2 — Collect sub-account identifier (if applicable), Step 3 — Collect operation-specific parameters, Step 4 — Confirm (prod-live write ops only), Step 5 — Execute and report

### Community 86 - "III. Order Queries"
Cohesion: 0.29
Nodes (7): 10. Query All Current Open Orders, 11. Order History, 12. Liquidation / Force Close Order Query, 13. Trade Fill History, 8. Query Single Open Order Status, 9. Query Order Details, III. Order Queries

### Community 87 - "V. Leverage and Mode Settings"
Cohesion: 0.29
Nodes (7): 17. Query Margin Mode, 18. Switch Margin Mode, 19. Query Leverage and Available Position, 20. Set Leverage, 21. Query Position Mode, 22. Set Position Mode, V. Leverage and Mode Settings

### Community 88 - "Subscribe Market Depth Data"
Cohesion: 0.29
Nodes (7): dataType Format, Parameters, Response Example, Response Fields, Subscribe Market Depth Data, Subscription Request, Timestamp Semantics

### Community 89 - "API Endpoints"
Cohesion: 0.29
Nodes (6): 1. Get All Orders, 2. Get All Fill Orders, API Endpoints, Chart Descriptions, Metric Benchmarks, Statistics Metric Definitions

### Community 90 - "model"
Cohesion: 0.29
Nodes (7): embargo_pct, n_splits, purge_pct, model, cross_validation, task, type

### Community 91 - "exchange"
Cohesion: 0.29
Nodes (7): exchange, name, paper_trading, rate_limit, symbols, testnet, timeframe

### Community 94 - "Parameters"
Cohesion: 0.33
Nodes (6): Enums, Order Parameters, Parameter Validation Rules, Parameters, Position Parameters, Stop-Loss / Take-Profit Object

### Community 95 - "Subscription: Limited Depth"
Cohesion: 0.33
Nodes (6): dataType Format, Parameters, Response Fields, Subscription: Limited Depth, Subscription Request, Supported Levels

### Community 96 - "Subscription: K-Line Data"
Cohesion: 0.33
Nodes (6): dataType Format, Parameters, Response Fields, Subscription: K-Line Data, Subscription Request, Supported Intervals

### Community 97 - "CCXTFetcher"
Cohesion: 0.07
Nodes (10): main(), CCXTFetcher, FeaturePipeline, TestDashboardBDDScenarios, TestTypeSafeBDDScenarios, TestZeroDataLeakageBDDScenarios, test_feature_data_leakage(), test_modular_evaluator_with_custom_model() (+2 more)

### Community 98 - "Subscription: Market Depth"
Cohesion: 0.33
Nodes (6): dataType Format, Parameters, Response Fields, Subscription: Market Depth, Subscription Request, Supported Levels

### Community 99 - "Subscription: Incremental and Full Depth"
Cohesion: 0.33
Nodes (6): dataType Format, How to Maintain Incremental Depth Locally, Parameters, Response Fields, Subscription: Incremental and Full Depth, Subscription Request

### Community 100 - "Subscription: K-Line Streams"
Cohesion: 0.33
Nodes (6): dataType Format, Parameters, Response Fields, Subscription: K-Line Streams, Subscription Request, Supported Intervals

### Community 101 - "2. Sub-account Lifecycle"
Cohesion: 0.33
Nodes (6): 2.1 Create Sub-account, 2.2 Get Sub-account List, 2.3 Query Sub-account Fund Assets, 2.4 Freeze / Unfreeze Sub-account, 2.5 Batch Query Sub-account Asset Overview, 2. Sub-account Lifecycle

### Community 102 - "Parameters"
Cohesion: 0.33
Nodes (6): API Key Parameters, Enums, Parameter Validation Rules, Parameters, Sub-account Parameters, Transfer Parameters

### Community 103 - "VII. TWAP Orders"
Cohesion: 0.33
Nodes (6): 26. Place TWAP Order, 27. Cancel TWAP Order, 28. Query TWAP Open Orders, 29. Query TWAP Historical Orders, 30. TWAP Order Details, VII. TWAP Orders

### Community 104 - "Subscribe K-Line Data"
Cohesion: 0.33
Nodes (6): dataType Format, Parameters, Response Fields, Subscribe K-Line Data, Subscription Request, Supported Intervals

### Community 105 - "Subscribe the Latest Trade Detail"
Cohesion: 0.33
Nodes (6): dataType Format, Parameters, Response Example, Response Fields, Subscribe the Latest Trade Detail, Subscription Request

### Community 106 - "backtest"
Cohesion: 0.33
Nodes (6): backtest, confidence_threshold, initial_capital, maker_fee, slippage, taker_fee

### Community 108 - "journal/__init__.py"
Cohesion: 0.13
Nodes (6): JournalAnalyzer, MarketSnapshot, ReviewNote, TradeTrajectory, temp_journal_env(), test_journal_analyzer_thesis()

### Community 110 - "Subscription: Trade Detail"
Cohesion: 0.40
Nodes (5): dataType Format, Parameters, Response Fields, Subscription Request, Subscription: Trade Detail

### Community 111 - "Subscription: Best Bid and Ask (Book Ticker)"
Cohesion: 0.40
Nodes (5): dataType Format, Parameters, Response Fields, Subscription: Best Bid and Ask (Book Ticker), Subscription Request

### Community 112 - "Subscription: Latest Trade Price"
Cohesion: 0.40
Nodes (5): dataType Format, Parameters, Response Fields, Subscription: Latest Trade Price, Subscription Request

### Community 113 - "Subscription: Mark Price"
Cohesion: 0.40
Nodes (5): dataType Format, Parameters, Response Fields, Subscription: Mark Price, Subscription Request

### Community 114 - "Subscription: Trade Detail"
Cohesion: 0.40
Nodes (5): dataType Format, Parameters, Response Fields, Subscription Request, Subscription: Trade Detail

### Community 115 - "Subscription: 24-Hour Price Change"
Cohesion: 0.40
Nodes (5): dataType Format, Parameters, Response Fields, Subscription: 24-Hour Price Change, Subscription Request

### Community 116 - "Subscription: Latest Trade Price"
Cohesion: 0.40
Nodes (5): dataType Format, Parameters, Response Fields, Subscription: Latest Trade Price, Subscription Request

### Community 117 - "Agent Interaction Rules"
Cohesion: 0.40
Nodes (5): Agent Interaction Rules, Depth level handling, Operation Identification, When kline interval is missing, When symbol is missing

### Community 118 - "1. Account Identity"
Cohesion: 0.40
Nodes (5): 1.1 Query Account UID, 1.2 Query API Key Permissions, 1.3 Query API Key Restrictions, 1.4 Query API Key Info, 1. Account Identity

### Community 119 - "Appendix: Enum Reference"
Cohesion: 0.40
Nodes (5): Account Category (fromType / toType), Account Type Codes, API Key Permissions, Appendix: Enum Reference, Deposit Status

### Community 120 - "VIII. Multi-Assets Mode"
Cohesion: 0.40
Nodes (5): 31. Query Multi-Assets Mode, 32. Switch Multi-Assets Mode, 33. Query Multi-Assets Rules, 34. Query Multi-Assets Margin, VIII. Multi-Assets Mode

### Community 121 - "II. Cancel Orders"
Cohesion: 0.40
Nodes (5): 4. Cancel Single Order, 5. Batch Cancel Orders, 6. Cancel All Open Orders, 7. Cancel All After (Kill Switch), II. Cancel Orders

### Community 122 - "BingX Swap WebSocket Market Data — API Reference"
Cohesion: 0.40
Nodes (3): BingX Swap WebSocket Market Data — API Reference, Connection, Error Codes

### Community 123 - "Subscribe to 24-Hour Price Changes"
Cohesion: 0.40
Nodes (5): dataType Format, Parameters, Response Fields, Subscribe to 24-Hour Price Changes, Subscription Request

### Community 124 - "Subscribe to Latest Price Changes"
Cohesion: 0.40
Nodes (5): dataType Format, Parameters, Response Fields, Subscribe to Latest Price Changes, Subscription Request

### Community 125 - "Subscribe to Latest Mark Price Changes"
Cohesion: 0.40
Nodes (5): dataType Format, Parameters, Response Fields, Subscribe to Latest Mark Price Changes, Subscription Request

### Community 126 - "Subscribe to Book Ticker Streams"
Cohesion: 0.40
Nodes (5): dataType Format, Parameters, Response Fields, Subscribe to Book Ticker Streams, Subscription Request

### Community 127 - "data"
Cohesion: 0.40
Nodes (5): data, cache_format, processed_dir, raw_dir, start_date

### Community 128 - "Agent Interaction Rules"
Cohesion: 0.50
Nodes (4): Agent Interaction Rules, Operation Identification, When kline interval is missing, When symbol is missing

### Community 129 - "Parameters"
Cohesion: 0.50
Nodes (4): Common Parameters, Enums, Parameter Validation Rules, Parameters

### Community 130 - "Parameters"
Cohesion: 0.50
Nodes (4): Common Parameters, Enums, Parameter Validation Rules, Parameters

### Community 131 - "IV. Position Management"
Cohesion: 0.50
Nodes (4): 14. Close All Positions, 15. Close Position by positionId, 16. Adjust Isolated Margin, IV. Position Management

### Community 132 - "Parameters"
Cohesion: 0.50
Nodes (4): Common Parameters, Enums, Parameter Validation Rules, Parameters

### Community 134 - "sys"
Cohesion: 0.09
Nodes (3): main(), RollingEvaluationResult, DataManager

### Community 146 - "交易學習日誌：SWAP_20261103_140101_LONG"
Cohesion: 0.18
Nodes (10): 1. 進場立論假說 (Trade Thesis), 2. 出場歸因 (Exit Catalyst), 3. 策略執行評價 (Strategy Evaluation), 4. 給操盤手的學習心得與啟發 (Pedagogical Takeaway), 一、基本交易參數, 三、前置風控計畫 (Pre-Trade Risk Management), 二、進場環境與技術面快照, 五、學習覆盤與策略反思 (Pedagogical Reflection) (+2 more)

### Community 154 - "test_bingx_gateway.py"
Cohesion: 0.11
Nodes (4): TestBingXBDDScenarios, test_domain_fallback(), test_param_validation(), test_symbol_normalization()

### Community 157 - "交易學習日誌：SWAP_20261104_021851_LONG"
Cohesion: 0.18
Nodes (10): 1. 進場立論假說 (Trade Thesis), 2. 出場歸因 (Exit Catalyst), 3. 策略執行評價 (Strategy Evaluation), 4. 給操盤手的學習心得與啟發 (Pedagogical Takeaway), 一、基本交易參數, 三、前置風控計畫 (Pre-Trade Risk Management), 二、進場環境與技術面快照, 五、學習覆盤與策略反思 (Pedagogical Reflection) (+2 more)

### Community 162 - "交易學習日誌：SWAP_20261104_015145_SHORT"
Cohesion: 0.18
Nodes (10): 1. 進場立論假說 (Trade Thesis), 2. 出場歸因 (Exit Catalyst), 3. 策略執行評價 (Strategy Evaluation), 4. 給操盤手的學習心得與啟發 (Pedagogical Takeaway), 一、基本交易參數, 三、前置風控計畫 (Pre-Trade Risk Management), 二、進場環境與技術面快照, 五、學習覆盤與策略反思 (Pedagogical Reflection) (+2 more)

### Community 166 - "overnight_swap_bot.py"
Cohesion: 0.15
Nodes (10): configure_bot_paths(), execute_swap_close(), execute_swap_open(), handle_exit(), load_state(), log_msg(), main(), save_state() (+2 more)

### Community 172 - "交易學習日誌：SWAP_20261104_002045_SHORT"
Cohesion: 0.18
Nodes (10): 1. 進場立論假說 (Trade Thesis), 2. 出場歸因 (Exit Catalyst), 3. 策略執行評價 (Strategy Evaluation), 4. 給操盤手的學習心得與啟發 (Pedagogical Takeaway), 一、基本交易參數, 三、前置風控計畫 (Pre-Trade Risk Management), 二、進場環境與技術面快照, 五、學習覆盤與策略反思 (Pedagogical Reflection) (+2 more)

### Community 175 - "交易學習日誌：SWAP_20261104_022601_LONG"
Cohesion: 0.18
Nodes (10): 1. 進場立論假說 (Trade Thesis), 2. 出場歸因 (Exit Catalyst), 3. 策略執行評價 (Strategy Evaluation), 4. 給操盤手的學習心得與啟發 (Pedagogical Takeaway), 一、基本交易參數, 三、前置風控計畫 (Pre-Trade Risk Management), 二、進場環境與技術面快照, 五、學習覆盤與策略反思 (Pedagogical Reflection) (+2 more)

### Community 176 - "交易學習日誌：SWAP_20261104_023102_LONG"
Cohesion: 0.18
Nodes (10): 1. 進場立論假說 (Trade Thesis), 2. 出場歸因 (Exit Catalyst), 3. 策略執行評價 (Strategy Evaluation), 4. 給操盤手的學習心得與啟發 (Pedagogical Takeaway), 一、基本交易參數, 三、前置風控計畫 (Pre-Trade Risk Management), 二、進場環境與技術面快照, 五、學習覆盤與策略反思 (Pedagogical Reflection) (+2 more)

### Community 177 - "交易學習日誌：SWAP_20261104_030108_LONG"
Cohesion: 0.18
Nodes (10): 1. 進場立論假說 (Trade Thesis), 2. 出場歸因 (Exit Catalyst), 3. 策略執行評價 (Strategy Evaluation), 4. 給操盤手的學習心得與啟發 (Pedagogical Takeaway), 一、基本交易參數, 三、前置風控計畫 (Pre-Trade Risk Management), 二、進場環境與技術面快照, 五、學習覆盤與策略反思 (Pedagogical Reflection) (+2 more)

### Community 178 - "INDEX.md"
Cohesion: 0.50
Nodes (3): 一、總體績效指標 (Overall Statistics), 二、歷史交易日誌清單 (Trade Entries), 量化交易自主學習日誌總覽 (Trade Journal Index)

### Community 179 - "交易學習日誌：SWAP_20261104_030257_LONG"
Cohesion: 0.18
Nodes (10): 1. 進場立論假說 (Trade Thesis), 2. 出場歸因 (Exit Catalyst), 3. 策略執行評價 (Strategy Evaluation), 4. 給操盤手的學習心得與啟發 (Pedagogical Takeaway), 一、基本交易參數, 三、前置風控計畫 (Pre-Trade Risk Management), 二、進場環境與技術面快照, 五、學習覆盤與策略反思 (Pedagogical Reflection) (+2 more)

### Community 182 - "交易學習日誌：SWAP_20261104_031009_LONG"
Cohesion: 0.18
Nodes (10): 1. 進場立論假說 (Trade Thesis), 2. 出場歸因 (Exit Catalyst), 3. 策略執行評價 (Strategy Evaluation), 4. 給操盤手的學習心得與啟發 (Pedagogical Takeaway), 一、基本交易參數, 三、前置風控計畫 (Pre-Trade Risk Management), 二、進場環境與技術面快照, 五、學習覆盤與策略反思 (Pedagogical Reflection) (+2 more)

### Community 185 - "交易學習日誌：SWAP_20261104_033213_LONG"
Cohesion: 0.18
Nodes (10): 1. 進場立論假說 (Trade Thesis), 2. 出場歸因 (Exit Catalyst), 3. 策略執行評價 (Strategy Evaluation), 4. 給操盤手的學習心得與啟發 (Pedagogical Takeaway), 一、基本交易參數, 三、前置風控計畫 (Pre-Trade Risk Management), 二、進場環境與技術面快照, 五、學習覆盤與策略反思 (Pedagogical Reflection) (+2 more)

### Community 188 - "cli/interactive_menu.py"
Cohesion: 0.29
Nodes (3): main(), main(), print_banner()

### Community 189 - "calculator.py"
Cohesion: 0.44
Nodes (6): calc_atr(), calc_sl(), calc_tp(), find_structure(), load_df(), main()

### Community 190 - "sentiment.py"
Cohesion: 0.39
Nodes (7): classify_fear_greed(), label(), main(), score_ahr999(), score_fear_greed(), score_funding(), score_oi()

### Community 193 - "analyze.py"
Cohesion: 0.39
Nodes (5): compute_score(), detect_divergence(), extract_latest(), find_support_resistance(), main()

### Community 196 - "ahr999.py"
Cohesion: 0.53
Nodes (4): exp_growth_value(), main(), normalize_klines(), zone_info()

### Community 198 - "streamlit"
Cohesion: 0.16
Nodes (4): inject_responsive_css(), render_gold_macro_card(), render_market_pulse_card(), TestResponsiveDashboardBDDScenarios

### Community 199 - "argparse"
Cohesion: 0.27
Nodes (7): classify(), main(), main(), build_plan(), calc_atr(), main(), snap_to_sr()

## Knowledge Gaps
- **1 isolated node(s):** `crypto-ai-quant`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1522 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **36 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BingXGateway` connect `BingXGateway` to `execution/__init__.py`, `pandas`, `BingXClient`, `overnight_swap_bot.py`, `sys`, `test_bingx.py`, `execution/__init__.py`, `BingXWebSocketClient`, `TestNativeStopLossAndDisconnectionBDDScenarios`, `overview_tab.py`, `json`, `PaperBroker`, `dashboard/app.py`, `test_bingx_gateway.py`, `overnight_trading_bot.py`, `.test_scenario_gateway_hybrid_prioritization_and_fallback`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `BingXGateway` (e.g. with `MarketType` and `BingXClient`) actually correct?**
  _`BingXGateway` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `crypto-ai-quant` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `BollingerBreakoutModel` be split into smaller, more focused modules?**
  _Cohesion score 0.12380952380952381 - nodes in this community are weakly interconnected._
- **Why does `UnifiedAutopilotEngine` connect `UnifiedAutopilotEngine` to `pandas`, `.evaluate_signal_choice`, `TestAutonomousOrchestrationBDDScenarios`, `overnight_swap_bot.py`, `execution/__init__.py`, `TestNativeStopLossAndDisconnectionBDDScenarios`, `.on_trade_open`, `overview_tab.py`, `TradeJournalEntry`, `dashboard/app.py`, `.test_scenario_autopilot_test_directory_journal_isolation`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `TradeJournalManager` (e.g. with `5. BDD 規格驅動測試矩陣 (BDD Test Matrix)` and `print_list_view()`) actually correct?**
  _`TradeJournalManager` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Should `BingXClient` be split into smaller, more focused modules?**
  _Cohesion score 0.06545879602571596 - nodes in this community are weakly interconnected._