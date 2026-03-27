from __future__ import annotations

import os
from dataclasses import dataclass


def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v


@dataclass(frozen=True)
class BotConfig:
    symbols: list[str]
    eta: float

    polygon_api_key: str

    alpaca_key_id: str
    alpaca_secret_key: str
    alpaca_paper: bool

    timezone: str = "America/New_York"
    exchange_calendar: str = "XNYS"

    band_abs: float = 0.01
    band_rel: float = 0.10
    min_trade_notional: float = 10.0
    cash_buffer_pct: float = 0.01

    strategy_version: str = "mwu_v1"
    sqlite_path: str = "bot_state.sqlite"


def load_config_from_env() -> BotConfig:
    symbols = os.getenv("BOT_SYMBOLS", "SPY,QQQ,TLT,IEF,GLD,JNJ,PG,WMT,XLU,VNQ")
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise RuntimeError("BOT_SYMBOLS is empty.")

    eta = float(os.getenv("BOT_ETA", "0.5"))

    polygon_api_key = _require_env("POLYGON_API_KEY")

    alpaca_key_id = _require_env("ALPACA_KEY_ID")
    alpaca_secret_key = _require_env("ALPACA_SECRET_KEY")
    alpaca_paper = os.getenv("ALPACA_PAPER", "true").lower() in {"1", "true", "yes", "y"}

    timezone = os.getenv("BOT_TIMEZONE", "America/New_York")
    exchange_calendar = os.getenv("BOT_EXCHANGE_CALENDAR", "XNYS")

    band_abs = float(os.getenv("BOT_BAND_ABS", "0.01"))
    band_rel = float(os.getenv("BOT_BAND_REL", "0.10"))
    min_trade_notional = float(os.getenv("BOT_MIN_TRADE_NOTIONAL", "10.0"))
    cash_buffer_pct = float(os.getenv("BOT_CASH_BUFFER_PCT", "0.01"))

    sqlite_path = os.getenv("BOT_SQLITE_PATH", "bot_state.sqlite")

    return BotConfig(
        symbols=symbol_list,
        eta=eta,
        polygon_api_key=polygon_api_key,
        alpaca_key_id=alpaca_key_id,
        alpaca_secret_key=alpaca_secret_key,
        alpaca_paper=alpaca_paper,
        timezone=timezone,
        exchange_calendar=exchange_calendar,
        band_abs=band_abs,
        band_rel=band_rel,
        min_trade_notional=min_trade_notional,
        cash_buffer_pct=cash_buffer_pct,
        sqlite_path=sqlite_path,
    )

