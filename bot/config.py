from __future__ import annotations

import os
from dataclasses import dataclass


def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v


def _parse_csv_syms(v: str) -> list[str]:
    return [s.strip().upper() for s in v.split(",") if s.strip()]


def _parse_symbol_tags(v: str) -> dict[str, str]:
    """
    Format: "SPY=equity_us,TLT=bonds_long,GLD=gold,AAPL=tech"
    """
    out: dict[str, str] = {}
    for chunk in v.split(","):
        c = chunk.strip()
        if not c:
            continue
        if "=" not in c:
            raise RuntimeError("BOT_SYMBOL_TAGS must be comma-separated KEY=VALUE pairs")
        k, val = c.split("=", 1)
        sym = k.strip().upper()
        tag = val.strip()
        if not sym or not tag:
            raise RuntimeError("BOT_SYMBOL_TAGS contains an empty key or value")
        out[sym] = tag
    return out


DEFAULT_CANDIDATE_POOL = [
    # Broad US equity
    "SPY",
    "VTI",
    "QQQ",
    "IWM",
    # International equity
    "VEA",
    "VWO",
    # Bonds
    "SHY",
    "IEF",
    "TLT",
    "LQD",
    # Alternatives / inflation hedges
    "GLD",
    "DBC",
    "VNQ",
    # Defensive sector ETFs
    "XLP",
    "XLU",
    "XLV",
]

DEFAULT_SYMBOL_TAGS: dict[str, str] = {
    "SPY": "equity_us",
    "VTI": "equity_us",
    "QQQ": "equity_us",
    "IWM": "equity_us",
    "VEA": "equity_intl",
    "VWO": "equity_intl",
    "SHY": "bonds_short",
    "IEF": "bonds_int",
    "TLT": "bonds_long",
    "LQD": "credit",
    "GLD": "gold",
    "DBC": "commodities",
    "VNQ": "real_estate",
    "XLP": "sector_defensive",
    "XLU": "sector_defensive",
    "XLV": "sector_defensive",
}

DEFAULT_SAFE_CATEGORIES = {"bonds_short", "bonds_int", "bonds_long", "credit", "gold"}


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

    dry_run: bool = False

    strategy_version: str = "mwu_v1"
    sqlite_path: str = "bot_state.sqlite"

    candidate_pool: list[str] | None = None
    symbol_tags: dict[str, str] | None = None
    safe_categories: set[str] | None = None
    universe_size: int | None = None
    universe_safe_min: int = 0
    universe_max_per_category: int | None = None
    score_lookback_days: int = 90
    score_metric: str = "momentum_return"  # momentum_return|risk_adjusted
    out_of_universe_positions: str = "ignore"  # ignore|warn_and_skip|liquidate


def load_config_from_env() -> BotConfig:
    symbols = os.getenv("BOT_SYMBOLS", "SPY,QQQ,TLT,IEF,GLD,JNJ,PG,WMT,XLU,VNQ")
    symbol_list = _parse_csv_syms(symbols)
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

    dry_run = os.getenv("BOT_DRY_RUN", "false").lower() in {"1", "true", "yes", "y"}

    sqlite_path = os.getenv("BOT_SQLITE_PATH", "bot_state.sqlite")

    candidate_pool_raw = os.getenv("BOT_CANDIDATE_POOL")
    candidate_pool = _parse_csv_syms(candidate_pool_raw) if candidate_pool_raw else None

    symbol_tags_raw = os.getenv("BOT_SYMBOL_TAGS")
    symbol_tags = _parse_symbol_tags(symbol_tags_raw) if symbol_tags_raw else None

    safe_categories_raw = os.getenv("BOT_SAFE_CATEGORIES")
    safe_categories = {s.strip() for s in safe_categories_raw.split(",") if s.strip()} if safe_categories_raw else None

    universe_size_raw = os.getenv("BOT_UNIVERSE_SIZE")
    universe_size = int(universe_size_raw) if universe_size_raw else None

    universe_safe_min = int(os.getenv("BOT_UNIVERSE_SAFE_MIN", "2"))

    universe_max_per_category_raw = os.getenv("BOT_UNIVERSE_MAX_PER_CATEGORY")
    universe_max_per_category = int(universe_max_per_category_raw) if universe_max_per_category_raw else 2

    score_lookback_days = int(os.getenv("BOT_SCORE_LOOKBACK_DAYS", "90"))
    score_metric = os.getenv("BOT_SCORE_METRIC", "momentum_return").strip()

    out_of_universe_positions = os.getenv("BOT_OUT_OF_UNIVERSE_POSITIONS", "ignore").strip()

    # Sane defaults: setting only BOT_UNIVERSE_SIZE enables auto-selection
    # using a built-in diversified pool + categories.
    if universe_size is not None:
        if candidate_pool is None:
            candidate_pool = list(DEFAULT_CANDIDATE_POOL)
        if symbol_tags is None:
            symbol_tags = dict(DEFAULT_SYMBOL_TAGS)
        if safe_categories is None:
            safe_categories = set(DEFAULT_SAFE_CATEGORIES)

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
        dry_run=dry_run,
        sqlite_path=sqlite_path,
        candidate_pool=candidate_pool,
        symbol_tags=symbol_tags,
        safe_categories=safe_categories,
        universe_size=universe_size,
        universe_safe_min=universe_safe_min,
        universe_max_per_category=universe_max_per_category,
        score_lookback_days=score_lookback_days,
        score_metric=score_metric,
        out_of_universe_positions=out_of_universe_positions,
    )

