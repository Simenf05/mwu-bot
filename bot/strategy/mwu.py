from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MWUParams:
    eta: float


def normalize_weights(w: np.ndarray) -> np.ndarray:
    s = float(np.sum(w))
    if not np.isfinite(s) or s <= 0:
        raise ValueError("Cannot normalize non-positive or non-finite weight sum.")
    return w / s


def update_weights_mwu(weights: np.ndarray, asset_returns: np.ndarray, params: MWUParams) -> np.ndarray:
    """
    Exponentiated-gradient style MWU update used in main.py:
      w_new ∝ w * exp(eta * r)
    """
    if weights.shape != asset_returns.shape:
        raise ValueError("weights and asset_returns must have same shape.")
    new_weights = weights * np.exp(params.eta * asset_returns)
    return normalize_weights(new_weights)


def drift_weights(weights: np.ndarray, asset_returns: np.ndarray) -> np.ndarray:
    """
    Portfolio drift after returns and before rebalancing:
      w_drift = w*(1+r) / (1 + dot(w, r))
    """
    if weights.shape != asset_returns.shape:
        raise ValueError("weights and asset_returns must have same shape.")
    portfolio_return = float(np.dot(weights, asset_returns))
    denom = 1.0 + portfolio_return
    if denom <= 0 or not np.isfinite(denom):
        raise ValueError("Invalid portfolio return for drift computation.")
    drifted = weights * (1.0 + asset_returns) / denom
    return normalize_weights(drifted)

