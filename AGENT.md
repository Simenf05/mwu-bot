## Project Overview

This repository implements a **live trading bot** that uses **Multiplicative Weights Update (MWU)** to dynamically **rebalance a portfolio of liquid ETFs/equities**. It is designed for **daily, fully automated operation** using:

- **Data**: Polygon (daily close prices)
- **Execution/broker**: Alpaca (`alpaca-py`)
- **Scheduling**: APScheduler (runs once per trading day, typically 15:45 America/New_York)
- **Trading calendar**: `exchange-calendars` (handles holidays/early closes)
- **Persistent state**: SQLite via SQLAlchemy (default file: `bot_state.sqlite`)

There are two main usage modes:

- **Production bot** (under `bot/`): daily, idempotent live/paper trading.
- **Research/backtesting** (under `scripts/`): MWU strategy exploration and backtests.

The codebase is already structured for **systemd-based deployment** on common Linux distros (see `packaging/` and `packaging/install.sh`).

---

## High-Level Behavior

On each trading day, after new market data is available, the bot:

1. **Loads configuration** from environment variables (or `.env`) via `bot.config`.
2. **Fetches latest daily close prices** for the configured symbol universe from Polygon.
3. **Updates MWU weights** based on asset returns and the MWU learning rate parameter \(\eta\) (e.g. `BOT_ETA`).
4. **Computes target portfolio weights** and notional allocations (subject to bands and minimum trade sizes).
5. **Checks Alpaca positions and cash**, then generates orders needed to move the portfolio toward the MWU targets.
6. **Applies trade bands and cash buffer** so that very small or noisy changes are ignored and a cash cushion is retained.
7. **Submits orders to Alpaca** (paper or live, depending on configuration).
8. **Persists run state** (e.g. weights, last run date, etc.) to SQLite so runs are **idempotent** for a given day.

The **scheduler** (`bot.scheduler`) typically runs once per day and calls a function like `run_one_session` in `bot.run_daily` for the current trading date. Manual, single-run invocation for testing is supported (see `README.md`).

---

## Key Directories and Files

- `bot/`
  - **Core production bot implementation**.
  - Contains:
    - Configuration loading (env vars / `.env`).
    - MWU portfolio logic and state management.
    - Alpaca integration (orders, positions, account).
    - Scheduler entrypoint (`bot.scheduler`).
- `scripts/`
  - **Research and backtesting** utilities.
  - Not intended for production deployment, but useful for strategy exploration.
- `packaging/`
  - Cross-distro **systemd** deployment helpers.
  - `install.sh`: installs the bot into `/opt/mwu-bot`, sets up a virtualenv, and installs a systemd unit.
  - `PKGBUILD.mwu-bot-git`: Arch Linux packaging for AUR-style distribution.
- `requirements.txt`
  - Python dependencies for the bot and research scripts.
- `README.md`
  - Human-focused quickstart (install, config, running, and packaging notes).

Agents should generally treat `bot/` as the **source of truth** for production behavior and ensure changes remain compatible with the deployment model in `packaging/`.

---

## Configuration and Environment

Core configuration is via **environment variables** (or `.env` loaded by `python-dotenv`). Key ones:

- **API keys and auth**
  - `POLYGON_API_KEY`
  - `ALPACA_KEY_ID`
  - `ALPACA_SECRET_KEY`
- **Trading / execution settings**
  - `ALPACA_PAPER` (default `true`): paper vs. live trading.
  - `BOT_SYMBOLS`: comma-separated ticker list (universe the MWU algorithm trades).
  - `BOT_ETA`: MWU learning rate (higher = more responsive, higher turnover).
  - `BOT_BAND_ABS`, `BOT_BAND_REL`: absolute/relative rebalance thresholds; used to avoid micro-trades.
  - `BOT_MIN_TRADE_NOTIONAL`: minimum dollar size for placing an order.
  - `BOT_CASH_BUFFER_PCT`: fraction of equity kept as cash (risk management / slippage buffer).
- **State and time handling**
  - `BOT_SQLITE_PATH`: path to the SQLite state DB (default `bot_state.sqlite`).
  - `BOT_TIMEZONE`: typically `America/New_York`.
  - `BOT_EXCHANGE_CALENDAR`: exchange calendar identifier (e.g. `XNYS`).

Agents modifying configuration behavior should:

- Keep env var names stable when possible, or update all references consistently.
- Maintain safe defaults (e.g. paper trading on by default, conservative cash buffer).
- Preserve idempotence and replayability: the same date/config should not cause double-trading.

---

## Scheduling and Deployment Model

- **Local / dev usage**
  - Activate the virtualenv, set env vars (or `.env`), and run:
    - `python -m bot.scheduler` for scheduled daily operation.
    - A one-off run via an inline script that calls `run_one_session`.
- **Systemd deployment (recommended for production)**
  - `packaging/install.sh` installs to `/opt/mwu-bot`, creates `.venv`, and sets up `mwu-bot.service`.
  - The systemd unit runs the scheduler (which in turn runs the daily MWU session).
  - Logs are retrieved via `journalctl -u mwu-bot.service -f`.

When changing entrypoints or CLI behavior, ensure:

- `python -m bot.scheduler` remains a stable, supported way to run the production bot.
- The systemd service and Arch `PKGBUILD.mwu-bot-git` stay in sync with any entrypoint changes.

---

## Expectations for Future Agents

- **Primary goal**: maintain and extend a **robust, automated MWU-based portfolio rebalancing bot** that interacts safely with real brokerage APIs.
- **Bias toward safety**:
  - Favor paper trading and small-scale tests before enabling real-money deployment.
  - Avoid breaking idempotence; it is critical that re-running for the same date does not multiply trades.
  - Respect trade bands, minimum notional sizes, and cash buffers to limit churn and operational risk.
- **Testing and validation**:
  - Use `scripts/backtest_mwu.py` and related tools when making changes to the MWU logic.
  - Prefer adding small, high-value tests around MWU weight updates, ordering logic, and state persistence.
- **Non-goals**:
  - This project is not a generic trading framework; avoid turning it into one unless explicitly asked.
  - Do not add unrelated ML/optimization features without clear integration into MWU-based portfolio management.

If you are unsure how a change might impact production behavior, inspect `bot/run_daily.py`, `bot/scheduler.py` (or similar core files) and the deployment scripts in `packaging/` to understand the full end-to-end flow before editing.

