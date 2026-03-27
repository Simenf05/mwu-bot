from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from bot.data.polygon_client import PolygonClient


@dataclass(frozen=True)
class UniverseSelectionParams:
    universe_size: int
    universe_safe_min: int
    universe_max_per_category: int | None
    safe_categories: set[str]
    lookback_days: int
    score_metric: str  # momentum_return|risk_adjusted


def _max_drawdown_from_closes(closes: list[float]) -> float:
    """
    closes: most-recent first.
    returns max drawdown as a fraction in [0, 1], computed over time from oldest->newest.
    """
    x = np.asarray(list(reversed(closes)), dtype=float)
    if x.size < 2 or not np.all(np.isfinite(x)):
        return 1.0
    peak = x[0]
    mdd = 0.0
    for v in x:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak)
    return float(mdd)


def _score_symbol(closes: list[float], metric: str) -> float:
    """
    closes: most-recent first.
    """
    if len(closes) < 3:
        return float("-inf")
    x = np.asarray(list(reversed(closes)), dtype=float)  # oldest -> newest
    if not np.all(np.isfinite(x)) or np.any(x <= 0):
        return float("-inf")

    total_return = float((x[-1] / x[0]) - 1.0)
    if metric == "momentum_return":
        return total_return

    if metric == "risk_adjusted":
        rets = np.diff(np.log(x))
        vol = float(np.std(rets, ddof=1)) if rets.size >= 2 else 0.0
        if vol <= 0 or not np.isfinite(vol):
            return float("-inf")
        return float(total_return / vol)

    raise ValueError("score_metric must be momentum_return|risk_adjusted")


def select_universe(
    *,
    session_date: date,
    polygon: PolygonClient,
    candidate_pool: list[str],
    symbol_tags: dict[str, str],
    params: UniverseSelectionParams,
) -> tuple[list[str], dict[str, float]]:
    """
    Returns (selected_symbols, scores_by_symbol).
    """
    pool = [s.strip().upper() for s in candidate_pool if s.strip()]
    if not pool:
        raise ValueError("candidate_pool is empty")
    if params.universe_size <= 0:
        raise ValueError("universe_size must be > 0")
    if params.universe_safe_min < 0:
        raise ValueError("universe_safe_min must be >= 0")
    if params.lookback_days <= 1:
        raise ValueError("lookback_days must be > 1")

    tags = {k.upper(): v for k, v in (symbol_tags or {}).items()}
    missing = [s for s in pool if s not in tags]
    if missing:
        raise RuntimeError(f"Missing BOT_SYMBOL_TAGS for: {', '.join(missing[:20])}" + (" ..." if len(missing) > 20 else ""))

    scores: dict[str, float] = {}
    categories: dict[str, str] = {}
    for sym in pool:
        closes = polygon.get_recent_daily_closes(sym, session_date, lookback_days=params.lookback_days)
        scores[sym] = _score_symbol(closes, params.score_metric)
        categories[sym] = tags[sym]

    sorted_syms = sorted(pool, key=lambda s: (scores.get(s, float("-inf"))), reverse=True)

    # 1) pick safe symbols first
    selected: list[str] = []
    per_cat: dict[str, int] = {}
    skipped_by_cat_cap: dict[str, int] = {}

    def can_add(sym: str) -> bool:
        cat = categories[sym]
        if params.universe_max_per_category is not None and per_cat.get(cat, 0) >= params.universe_max_per_category:
            skipped_by_cat_cap[cat] = skipped_by_cat_cap.get(cat, 0) + 1
            return False
        return True

    safe_syms = [s for s in sorted_syms if categories[s] in params.safe_categories]
    for sym in safe_syms:
        if len(selected) >= params.universe_safe_min:
            break
        if can_add(sym):
            selected.append(sym)
            per_cat[categories[sym]] = per_cat.get(categories[sym], 0) + 1

    # 2) fill remaining slots by score with diversification constraints
    for sym in sorted_syms:
        if sym in selected:
            continue
        if len(selected) >= params.universe_size:
            break
        if can_add(sym):
            selected.append(sym)
            per_cat[categories[sym]] = per_cat.get(categories[sym], 0) + 1

    if not selected:
        raise RuntimeError("Universe selection produced an empty universe")
    # Attach some selection diagnostics via NaN sentinel keys in scores map.
    # (Run-level logging will format/print these in a human readable way.)
    scores["__meta_pool_size__"] = float(len(pool))
    scores["__meta_selected_size__"] = float(len(selected))
    scores["__meta_safe_selected__"] = float(sum(1 for s in selected if categories[s] in params.safe_categories))
    scores["__meta_categories_used__"] = float(len(set(categories[s] for s in selected)))
    scores["__meta_skipped_by_cat_cap__"] = float(sum(skipped_by_cat_cap.values()))
    return selected, scores

