# XGE - Crypto Arbitrage & Basis Trade System

## What This Project Does

XGE is an automated crypto trading system that:
1. **Collects real-time prices** from multiple exchanges via WebSocket (ccxt.pro)
2. **Monitors funding rates** on perpetual contracts
3. **Executes basis trades**: long spot + short perp when funding rates are high, collecting the funding premium
4. **Sends email notifications** on trade open/close via Resend

## Architecture Overview

```
Data Collectors (WS) → Redis Cache → BasisTradeStrategy → TradeExecutor → PositionManager
                                                        ↘ EmailNotifier (optional)
```

## Directory Structure

```
src/xge/
├── config.py                    # Settings loader (YAML + env vars)
├── main.py                      # Async orchestrator, starts all components
├── models.py                    # OrderBookEntry, SpreadInfo
├── models_funding.py            # FundingRateEntry, SpotFundingArb, FundingRateSpread
├── models_trading.py            # TradeSignal, LegFill, Position
├── cache/redis_cache.py         # Async Redis wrapper
├── collector/
│   ├── ws_collector.py          # WebSocket price collector (per exchange)
│   └── funding_collector.py     # Funding rate collector (WS or REST fallback)
├── trading/
│   ├── strategy.py              # BasisTradeStrategy - entry/exit logic
│   ├── executor.py              # TradeExecutor - paper or live order execution
│   └── position_manager.py      # PositionManager - Redis position tracking
├── notifications/email.py       # EmailNotifier via Resend
└── utils/logger.py              # Logging setup
config/settings.yaml             # Main config file
```

## Key Models

- **OrderBookEntry**: Best bid/ask from an exchange for a symbol
- **FundingRateEntry**: Current funding rate for a perp contract
- **SpotFundingArb**: Detected basis trade opportunity (funding rate > threshold)
- **TradeSignal**: Generated when entry/exit conditions are met (action, exchange, symbol, reason)
- **LegFill**: Execution fill for one leg (price, quantity, fee)
- **Position**: Full trade state (entry/exit prices, quantities, P&L, status open/closed)

## Trading Logic (BasisTradeStrategy)

**Entry conditions** (in `_evaluate_entry`):
- Funding rate is positive
- Annualized rate >= `min_entry_annualized_pct` (default 10%)
- Position manager allows new position (under max limits)
- Action: buy spot + sell perp

**Exit conditions** (in `_evaluate_exit`):
- Funding rate turned negative, OR
- Annualized rate < `min_exit_annualized_pct` (default 3%)
- Action: sell spot + buy perp (close both legs)

**P&L**: `spot_pnl + perp_pnl + funding_collected`

## Configuration

Config loaded from `config/settings.yaml` with `${ENV_VAR:-default}` interpolation.

Key sections:
- **exchanges**: List with id, enabled, taker_fee_pct
- **symbols**: Trading pairs (e.g., BTC/USDT)
- **redis**: url, host, port
- **funding**: poll_interval, min_annualized_pct, excluded_exchanges
- **notifications**: enabled, resend_api_key, from_email, to_email
- **trading**: paper_trading, position_size_usdt, min_entry/exit thresholds, max_positions, exchanges list

## Current Setup

- **Paper trading** on OKX, Bitget, MEXC
- **$1000 per position**, max 1 per exchange, 3 total
- **Geo-blocked**: Binance, Bybit (disabled)
- **26 symbols** monitored (BTC, ETH, SOL, stablecoins, etc.)
- **Notifications** via Resend to sergio@platomico.com

## Environment Variables

- `REDIS_URL` / `REDIS_HOST` / `REDIS_PORT` — Redis connection
- `RESEND_API_KEY` — Resend email API key
- `NOTIFY_EMAIL` — Recipient email
- `NOTIFY_FROM` — Sender email (default: xge@resend.dev)
- `{EXCHANGE}_API_KEY`, `{EXCHANGE}_SECRET` — For live trading

## Dependencies

ccxt, protobuf, redis, pyyaml, python-dotenv, resend

## Deployment

Deployed on Railway (see `railway.toml`, `Dockerfile`). Uses Docker with Python 3.11+.

## Redis Keys

- `latest:{exchange}:{symbol}` — Price snapshots
- `funding:{exchange}:{symbol}` — Funding rates
- `position:{exchange}:{symbol}` — Open positions
- `trade_history` — List of closed positions
