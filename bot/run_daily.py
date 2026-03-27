from __future__ import annotations

import logging
from datetime import date, datetime

import exchange_calendars as ecals
import numpy as np
from dotenv import load_dotenv

from bot.broker.alpaca_client import AlpacaBroker
from bot.config import BotConfig, load_config_from_env
from bot.data.polygon_client import PolygonClient
from bot.rebalance.bands import (
    BandRebalanceParams,
    build_banded_rebalance_orders,
    compute_current_weights_from_market_values,
)
from bot.state.store import Store
from bot.strategy.mwu import MWUParams, drift_weights, update_weights_mwu
from bot.universe.select import UniverseSelectionParams, select_universe

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

        # 0) Select session universe (optional)
        session_symbols = list(cfg.symbols)
        if cfg.universe_size:
            log.info(
                "Universe selection enabled: K=%s lookback_days=%s metric=%s safe_min=%s max_per_cat=%s safe_cats=%s",
                cfg.universe_size,
                cfg.score_lookback_days,
                cfg.score_metric,
                cfg.universe_safe_min,
                cfg.universe_max_per_category,
                ",".join(sorted(cfg.safe_categories or set())) or "(none)",
            )
            log.info(
                "Candidate pool size=%d (custom=%s)",
                len(cfg.candidate_pool or []),
                "yes" if cfg.candidate_pool is not None else "no (using defaults)",
            )
            safe_cats = cfg.safe_categories or set()
            params_sel = UniverseSelectionParams(
                universe_size=int(cfg.universe_size),
                universe_safe_min=int(cfg.universe_safe_min),
                universe_max_per_category=cfg.universe_max_per_category,
                safe_categories=set(safe_cats),
                lookback_days=int(cfg.score_lookback_days),
                score_metric=str(cfg.score_metric),
            )
            session_symbols, scores = select_universe(
                session_date=session_date,
                polygon=polygon,
                candidate_pool=list(cfg.candidate_pool or cfg.symbols),
                symbol_tags=dict(cfg.symbol_tags or {s: "unknown" for s in (cfg.candidate_pool or cfg.symbols)}),
                params=params_sel,
            )
            log.info("Selected universe (%d): %s", len(session_symbols), ",".join(session_symbols))
            top5 = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:5]
            log.info("Top scores: %s", ", ".join([f"{k}={v:.4f}" for k, v in top5]))
            metas = {k: v for k, v in scores.items() if k.startswith("__meta_")}
            if metas:
                log.info(
                    "Universe diagnostics: pool=%s selected=%s safe_selected=%s categories_used=%s skipped_by_cat_cap=%s",
                    int(metas.get("__meta_pool_size__", float("nan"))),
                    int(metas.get("__meta_selected_size__", float("nan"))),
                    int(metas.get("__meta_safe_selected__", float("nan"))),
                    int(metas.get("__meta_categories_used__", float("nan"))),
                    int(metas.get("__meta_skipped_by_cat_cap__", float("nan"))),
                )

        # 1) Fetch prices + compute returns vector
        prices: dict[str, tuple[float, float]] = {}
        returns_vec: list[float] = []
        for sym in session_symbols:
            close, prev_close = polygon.get_last_two_daily_closes(sym, session_date)
            prices[sym] = (close, prev_close)
            returns_vec.append((close / prev_close) - 1.0)
        store.upsert_prices(session_date, prices)

        r = np.asarray(returns_vec, dtype=float)

        # 2) Load previous weights (or initialize equal)
        prev = store.get_latest_weights(session_symbols)
        if prev is None:
            w_prev = np.ones(len(session_symbols), dtype=float) / float(len(session_symbols))
            log.info("No previous weights found; initializing equal weights across %d symbols.", len(session_symbols))
        else:
            w_prev = np.asarray([float(prev[s]) for s in session_symbols], dtype=float)
            s = float(np.sum(w_prev))
            if not np.isfinite(s) or s <= 0:
                w_prev = np.ones(len(session_symbols), dtype=float) / float(len(session_symbols))
                log.warning(
                    "Previous weights invalid for current universe (sum=%s). Re-initializing equal weights.", s
                )
            else:
                w_prev = w_prev / s

        # 3) Drift + MWU update
        w_drift = drift_weights(w_prev, r)
        w_new = update_weights_mwu(w_prev, r, MWUParams(eta=cfg.eta))

        target_weights = {sym: float(w_new[i]) for i, sym in enumerate(session_symbols)}
        store.upsert_weights(session_date, target_weights)

        # 4) Compute current weights from Alpaca positions
        acct = broker.get_account()
        pos = broker.get_positions()
        mv_map_all = {p.symbol.upper(): float(p.market_value) for p in pos}
        held_outside = sorted([s for s in mv_map_all.keys() if s not in set(session_symbols)])
        if held_outside:
            log.warning(
                "Detected %d held symbols outside universe (%s mode): %s",
                len(held_outside),
                cfg.out_of_universe_positions,
                ",".join(held_outside),
            )
        if held_outside and cfg.out_of_universe_positions == "warn_and_skip":
            msg = f"Held positions outside universe: {','.join(held_outside)}"
            log.error(msg)
            store.finish_run(run_id, status="failed", error=msg)
            return

        if held_outside and cfg.out_of_universe_positions == "liquidate":
            log.warning("Liquidating out-of-universe positions: %s", ",".join(held_outside))
            for sym in held_outside:
                if cfg.dry_run:
                    store.insert_order(
                        session_date=session_date,
                        symbol=sym,
                        side="sell",
                        notional=float(mv_map_all.get(sym, 0.0)),
                        alpaca_order_id="dry_run",
                        status="dry_run",
                    )
                else:
                    alpaca_order_id = broker.submit_notional_market_order(
                        sym, notional=float(mv_map_all.get(sym, 0.0)), side="sell"
                    )
                    store.insert_order(
                        session_date=session_date,
                        symbol=sym,
                        side="sell",
                        notional=float(mv_map_all.get(sym, 0.0)),
                        alpaca_order_id=alpaca_order_id,
                        status="submitted",
                    )

        # Ignore (default): size orders only to active universe + cash.
        mv_map = {s: float(mv_map_all.get(s, 0.0)) for s in session_symbols}
        params = BandRebalanceParams(
            band_abs=cfg.band_abs,
            band_rel=cfg.band_rel,
            min_trade_notional=cfg.min_trade_notional,
            cash_buffer_pct=cfg.cash_buffer_pct,
        )
        current_weights = compute_current_weights_from_market_values(
            session_symbols, mv_map, cash=acct.cash, params=params
        )
        active_portfolio_value = float(acct.cash) + sum(float(mv_map.get(s, 0.0)) for s in session_symbols)
        log.info(
            "Sizing context: cash=%.2f active_positions_value=%.2f active_portfolio_value=%.2f (account_portfolio_value=%.2f)",
            float(acct.cash),
            float(active_portfolio_value - float(acct.cash)),
            float(active_portfolio_value),
            float(acct.portfolio_value),
        )

        # 5) Build banded rebalance orders (sell-first)
        orders = build_banded_rebalance_orders(
            symbols=session_symbols,
            current_weights=current_weights,
            target_weights=target_weights,
            portfolio_value=active_portfolio_value,
            cash=acct.cash,
            params=params,
        )

        log.info("Computed %d orders for %s", len(orders), session_date)
        if orders:
            sells = [o for o in orders if str(o["side"]) == "sell"]
            buys = [o for o in orders if str(o["side"]) == "buy"]
            log.info(
                "Order summary: sells=%d ($%.2f) buys=%d ($%.2f)",
                len(sells),
                sum(float(o["notional"]) for o in sells),
                len(buys),
                sum(float(o["notional"]) for o in buys),
            )
            top_orders = sorted(orders, key=lambda o: float(o["notional"]), reverse=True)[:5]
            log.info(
                "Top orders: %s",
                ", ".join([f"{o['side']} {o['symbol']} ${float(o['notional']):.2f}" for o in top_orders]),
            )

        if cfg.dry_run:
            log.warning("BOT_DRY_RUN=true; not submitting orders to broker.")
            for o in orders:
                store.insert_order(
                    session_date=session_date,
                    symbol=str(o["symbol"]),
                    side=str(o["side"]),
                    notional=float(o["notional"]),
                    alpaca_order_id="dry_run",
                    status="dry_run",
                )
        else:
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


def _session_date_now(calendar_name: str, tz: str) -> date:
    cal = ecals.get_calendar(calendar_name)
    now = datetime.now(tz=cal.tz)  # calendar tz is typically America/New_York
    # If market is open today, use today's session date; otherwise last session.
    if cal.is_session(now.date()):
        return now.date()
    return cal.previous_session(now.date()).date()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    cfg = load_config_from_env()
    session_date = _session_date_now(cfg.exchange_calendar, cfg.timezone)

    log.info("Starting one-off session for %s", session_date)
    run_one_session(cfg, session_date=session_date)
    log.info("One-off session complete for %s", session_date)


if __name__ == "__main__":
    main()

