# Goal Description
Convert the offline Multiplicative Weights Update (MWU) backtesting algorithm into a fully autonomous, live-trading production bot.

## Recommendation (chosen)
- **Market data**: Polygon (REST) for bars/close prices
- **Broker/execution**: Alpaca (Paper first, then Live)
- **Rebalancing**: **banded** (only trade when drift/target deviation exceeds thresholds)

## Proposed tech stack (concrete)

### Runtime & packaging
- **Python**: keep using your local `.venv`, but add pinned dependencies via `requirements.txt` for reproducibility.
- **Project layout**: small package under `bot/` with clear module boundaries (data, broker, strategy, state, scheduling).

### Libraries
- **Polygon REST**: `requests` (+ `tenacity` for retries).
- **Alpaca trading**: `alpaca-py`
- **Scheduling**: `APScheduler`
- **Market sessions** (holidays/early closes): `exchange-calendars`
- **Persistence**: SQLite via `SQLAlchemy`
- **Config/secrets**: environment variables + `python-dotenv`
- **Logging**: built-in `logging`

### Deployment (simple, robust)
- **VM** (AWS EC2 / DigitalOcean) + `systemd` service
- Optional: Docker containerization once the bot is stable

## Architecture overview

### Module layout (target)
- `bot/config.py`: configuration + env var loading
- `bot/data/polygon_client.py`: fetch daily bars/close prices
- `bot/broker/alpaca_client.py`: positions, account, orders
- `bot/strategy/mwu.py`: MWU update + drift logic (extracted from `main.py`)
- `bot/rebalance/bands.py`: band thresholds + rebalance decision logic
- `bot/state/store.py`: SQLite schema + CRUD (runs, weights, orders, prices)
- `bot/run_daily.py`: one idempotent daily run
- `bot/scheduler.py`: APScheduler entrypoint (NY timezone + session checks)

### Data contracts
- **Strategy input**: close-to-close returns computed from Polygon daily close prices
- **Strategy output**: `target_weights: dict[str, float]` summing to 1
- **Execution input**: Alpaca positions + cash + latest prices
- **Execution output**: ordered trades (sell-first) with notional/qty constraints

## Daily run (idempotent) — concrete steps
1. **Session gate**: use `exchange-calendars` to confirm today is a trading day and determine session close time (handles early closes).
2. **Idempotency**: if `runs` table already contains a successful run for `session_date` + `strategy_version`, exit without trading.
3. **Fetch prices** (Polygon): download the last 2 daily closes per symbol and compute today’s returns.
4. **Load previous weights** from SQLite (or initialize equal weights on first run).
5. **Compute drifted weights** from observed returns.
6. **MWU update** to produce new target weights.
7. **Band filter**: only generate orders for symbols where deviation exceeds threshold; apply min-notional + cash buffer.
8. **Place orders**: submit **sells first**, then buys; persist all order ids + statuses.
9. **Persist state**: record weights/prices used and mark run as success/failure.

## Banded rebalancing (default rule)
- Trade symbol \(i\) only if:
\[
|w_{target,i} - w_{current,i}| > \max(band\_abs,\; band\_rel \cdot |w_{target,i}|)
\]
- Skip trades with notional below `min_trade_notional`
- Keep `cash_buffer_pct` unallocated to avoid insufficient buying power

## State & persistence (SQLite schema)
- `runs`: `session_date`, `started_at`, `finished_at`, `status`, `strategy_version`, `error`
- `weights`: `session_date`, `symbol`, `weight`
- `prices`: `session_date`, `symbol`, `close`, `prev_close`
- `orders`: `session_date`, `symbol`, `side`, `qty_or_notional`, `alpaca_order_id`, `status`

## Core Architectural Components Required

### 1. Market Data Feed (Real-Time)
`yfinance` is great for backtesting, but it is delayed and rate-limited. To run a live bot, you need a stable API.
- **Provider:** Alpaca API or Polygon.io.
- **Implementation:** The script will pull the current day's pricing data 15 minutes before the market closes to calculate the final returns.

### 2. Live Brokerage & Order Execution
The bot needs to convert the target weights calculated by the MWU into live `BUY` and `SELL` orders.
- **Provider:** [Alpaca](https://alpaca.markets/) (highly recommended for Python algorithms because it offers commission-free API trading and fractional shares).
- **Implementation:** 
  - Compare current portfolio holdings against the new MWU target weights.
  - Calculate the delta (what needs to be bought vs sold).
  - Submit REST API orders (`MARKET` or `LIMIT`) to execute the rebalancing.

### 3. Automated Cloud Hosting & Scheduling
Your laptop going to sleep will kill the bot. It needs to live in the cloud.
- **Hosting:** AWS EC2, DigitalOcean Droplet, or Heroku.
- **Scheduling:** Use `cron` (Linux) or `APScheduler` (Python) to automatically wake the bot up every trading day at exactly 3:45 PM EST to calculate the weights and submit the trades before the 4:00 PM closing bell.

## Proposed Changes / Phases

### Phase 1: Broker Integration
- Set up an Alpaca Paper Trading account (to test with fake money first).
- Install `alpaca-py`.
- Write a function `get_current_positions()` to read exactly what you currently own in the Alpaca account.

### Phase 2: Algorithm Modification
#### [MODIFY] [main.py](file:///home/simen/fintech/main.py)
- Remove the historical `for t in range(...)` backtest loop.
- Change the script structure so it only runs **one step** of the MWU equation per day, using yesterday's saved weights and today's new price data.

### Phase 3: Order Management System (OMS)
- Write an `execute_trades(target_weights)` function.
- **Critical Logic:** Sell orders MUST be executed *first* to free up the cash required to submit the subsequent buy orders.

## Verification Plan
1. **Paper Trading:** Run the bot on an Alpaca Paper Trading account for 2 weeks to ensure it correctly calculates the drift, submits the right fractional share orders, and doesn't crash on weekends or holidays.
2. **Slippage Evaluation:** Compare the live paper trading slippage against the mathematical `.0002` dynamic slippage model we built in the backtester to make sure reality matches the simulation.
