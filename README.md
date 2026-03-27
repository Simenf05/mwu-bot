# Live MWU Trading Bot (Polygon + Alpaca)

This repo contains:
- A research/backtest script (based on the original `main.py`)
- A production-oriented daily MWU bot under `bot/`

## Tech stack
- **Data**: Polygon (daily closes)
- **Execution**: Alpaca (`alpaca-py`)
- **Scheduling**: APScheduler (runs at 15:45 America/New_York by default)
- **Calendar**: `exchange-calendars` (handles holidays/early closes)
- **State**: SQLite via SQLAlchemy (`bot_state.sqlite`)

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration (env vars)

Required:
- `POLYGON_API_KEY`
- `ALPACA_KEY_ID`
- `ALPACA_SECRET_KEY`

Common optional:
- `ALPACA_PAPER=true` (default: true)
- `BOT_SYMBOLS=SPY,QQQ,TLT,IEF,GLD,JNJ,PG,WMT,XLU,VNQ`
- `BOT_ETA=0.5`
- `BOT_BAND_ABS=0.01`
- `BOT_BAND_REL=0.10`
- `BOT_MIN_TRADE_NOTIONAL=10`
- `BOT_CASH_BUFFER_PCT=0.01`
- `BOT_SQLITE_PATH=bot_state.sqlite`
- `BOT_TIMEZONE=America/New_York`
- `BOT_EXCHANGE_CALENDAR=XNYS`

You can also create a local `.env` file and the scheduler will load it (via `python-dotenv`).

## Run (paper trading first)

Run the scheduler (will run daily at 15:45 NY time and is idempotent):

```bash
python -m bot.scheduler
```

If you want to trigger a single run manually (example):

```bash
python -c "from datetime import date; from bot.config import load_config_from_env; from bot.run_daily import run_one_session; run_one_session(load_config_from_env(), date.today())"
```

## Backtest (research)

The original backtest is preserved in `scripts/backtest_mwu.py`:

```bash
python scripts/backtest_mwu.py
```

## Cross-distro systemd deployment

This repo includes a small `packaging/` directory to make deployment easy on Arch, Debian/Ubuntu, Fedora, etc.

- **Quick install on any systemd distro (root):**

```bash
cd /path/to/this/repo
sudo bash packaging/install.sh
```

This will:
- Copy the project into `/opt/mwu-bot`
- Create `/opt/mwu-bot/.venv` and install Python deps
- Create a skeleton `/opt/mwu-bot/.env` for you to fill with keys
- Install and start the `mwu-bot.service` systemd unit

Check logs with:

```bash
sudo journalctl -u mwu-bot.service -f
```

For Arch packaging, see `packaging/PKGBUILD.mwu-bot-git` as a starting point for an AUR package.

