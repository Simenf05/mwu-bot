from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BandRebalanceParams:
    band_abs: float = 0.01
    band_rel: float = 0.10
    min_trade_notional: float = 10.0
    cash_buffer_pct: float = 0.01


def should_trade_weight(current_w: float, target_w: float, params: BandRebalanceParams) -> bool:
    thresh = max(params.band_abs, params.band_rel * abs(target_w))
    return abs(target_w - current_w) > thresh


def compute_current_weights_from_market_values(
    symbols: list[str],
    symbol_to_market_value: dict[str, float],
    cash: float,
    params: BandRebalanceParams,
) -> dict[str, float]:
    """
    Compute portfolio weights from current market values plus cash.

    For rebalancing decisions we treat cash as part of the portfolio value, but
    execution will keep a cash buffer (params.cash_buffer_pct).
    """
    pv = float(cash) + sum(float(symbol_to_market_value.get(s, 0.0)) for s in symbols)
    if pv <= 0:
        raise ValueError("Non-positive portfolio value.")
    out: dict[str, float] = {}
    for s in symbols:
        mv = float(symbol_to_market_value.get(s, 0.0))
        out[s] = max(0.0, mv / pv)
    return out


def build_banded_rebalance_orders(
    *,
    symbols: list[str],
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    portfolio_value: float,
    cash: float,
    params: BandRebalanceParams,
) -> list[dict[str, float | str]]:
    """
    Build a sell-first order list based on weight deltas.

    Returns list of dicts:
      { "symbol": str, "side": "sell"|"buy", "notional": float }
    """
    if portfolio_value <= 0:
        raise ValueError("portfolio_value must be > 0")
    if not (0.0 <= params.cash_buffer_pct < 1.0):
        raise ValueError("cash_buffer_pct must be in [0,1)")

    # Keep some cash aside to reduce buying-power failures.
    target_investable_value = portfolio_value * (1.0 - params.cash_buffer_pct)

    deltas_notional: dict[str, float] = {}
    for s in symbols:
        cw = float(current_weights.get(s, 0.0))
        tw = float(target_weights.get(s, 0.0))
        if not should_trade_weight(cw, tw, params):
            continue
        deltas_notional[s] = (tw - cw) * target_investable_value

    sells: list[dict[str, float | str]] = []
    buys: list[dict[str, float | str]] = []
    for s, dn in deltas_notional.items():
        if abs(dn) < params.min_trade_notional:
            continue
        if dn < 0:
            sells.append({"symbol": s, "side": "sell", "notional": float(-dn)})
        else:
            buys.append({"symbol": s, "side": "buy", "notional": float(dn)})

    # If cash is insufficient for buys, scale them down proportionally.
    available_for_buys = max(0.0, float(cash) - portfolio_value * params.cash_buffer_pct)
    total_buy = sum(float(o["notional"]) for o in buys)
    if total_buy > 0 and available_for_buys > 0 and total_buy > available_for_buys:
        scale = available_for_buys / total_buy
        scaled: list[dict[str, float | str]] = []
        for o in buys:
            n = float(o["notional"]) * scale
            if n >= params.min_trade_notional:
                scaled.append({"symbol": str(o["symbol"]), "side": "buy", "notional": float(n)})
        buys = scaled

    # Sell-first ordering.
    return sells + buys

