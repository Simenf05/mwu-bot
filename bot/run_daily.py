from __future__ import annotations

import logging
from datetime import date

import numpy as np

from bot.broker.alpaca_client import AlpacaBroker
from bot.config import BotConfig
from bot.data.polygon_client import PolygonClient
from bot.rebalance.bands import (
    BandRebalanceParams,
    build_banded_rebalance_orders,
    compute_current_weights_from_market_values,
)
from bot.state.store import Store
from bot.strategy.mwu import MWUParams, drift_weights, update_weights_mwu

log = logging.getLogger(__name__)


def run_one_session(cfg: BotConfig, session_date: date) -> None:
    store = Store(cfg.sqlite_path)
    store.init_db()

    if store.run_success_exists(session_date, cfg.strategy_version):
        log.info("Run already successful for %s (%s); skipping.", session_date, cfg.strategy_version)
        return

    run_id = store.start_run(session_date, cfg.strategy_version)
    try:
        polygon = PolygonClient(api_key=cfg.polygon_api_key)
        broker = AlpacaBroker(cfg.alpaca_key_id, cfg.alpaca_secret_key, paper=cfg.alpaca_paper)

        # 1) Fetch prices + compute returns vector
        prices: dict[str, tuple[float, float]] = {}
        returns_vec: list[float] = []
        for sym in cfg.symbols:
            close, prev_close = polygon.get_last_two_daily_closes(sym, session_date)
            prices[sym] = (close, prev_close)
            returns_vec.append((close / prev_close) - 1.0)
        store.upsert_prices(session_date, prices)

        r = np.asarray(returns_vec, dtype=float)

        # 2) Load previous weights (or initialize equal)
        prev = store.get_latest_weights(cfg.symbols)
        if prev is None:
            w_prev = np.ones(len(cfg.symbols), dtype=float) / float(len(cfg.symbols))
        else:
            w_prev = np.asarray([float(prev[s]) for s in cfg.symbols], dtype=float)
            w_prev = w_prev / float(np.sum(w_prev))

        # 3) Drift + MWU update
        w_drift = drift_weights(w_prev, r)
        w_new = update_weights_mwu(w_prev, r, MWUParams(eta=cfg.eta))

        target_weights = {sym: float(w_new[i]) for i, sym in enumerate(cfg.symbols)}
        store.upsert_weights(session_date, target_weights)

        # 4) Compute current weights from Alpaca positions
        acct = broker.get_account()
        pos = broker.get_positions()
        mv_map = {p.symbol: p.market_value for p in pos}
        params = BandRebalanceParams(
            band_abs=cfg.band_abs,
            band_rel=cfg.band_rel,
            min_trade_notional=cfg.min_trade_notional,
            cash_buffer_pct=cfg.cash_buffer_pct,
        )
        current_weights = compute_current_weights_from_market_values(
            cfg.symbols, mv_map, cash=acct.cash, params=params
        )

        # 5) Build banded rebalance orders (sell-first)
        orders = build_banded_rebalance_orders(
            symbols=cfg.symbols,
            current_weights=current_weights,
            target_weights=target_weights,
            portfolio_value=acct.portfolio_value,
            cash=acct.cash,
            params=params,
        )

        log.info("Computed %d orders for %s", len(orders), session_date)

        for o in orders:
            symbol = str(o["symbol"])
            side = str(o["side"])
            notional = float(o["notional"])
            alpaca_order_id = broker.submit_notional_market_order(symbol, notional=notional, side=side)
            store.insert_order(
                session_date=session_date,
                symbol=symbol,
                side=side,
                notional=notional,
                alpaca_order_id=alpaca_order_id,
                status="submitted",
            )

        store.finish_run(run_id, status="success", error=None)
    except Exception as e:  # noqa: BLE001
        log.exception("Run failed for %s", session_date)
        store.finish_run(run_id, status="failed", error=str(e))
        raise

