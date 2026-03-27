from __future__ import annotations

from dataclasses import dataclass

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    qty: float
    market_value: float


@dataclass(frozen=True)
class AccountSnapshot:
    cash: float
    portfolio_value: float


class AlpacaBroker:
    def __init__(self, key_id: str, secret_key: str, paper: bool) -> None:
        self._client = TradingClient(key_id, secret_key, paper=paper)

    def get_account(self) -> AccountSnapshot:
        acct = self._client.get_account()
        return AccountSnapshot(
            cash=float(acct.cash),
            portfolio_value=float(acct.portfolio_value),
        )

    def get_positions(self) -> list[PositionSnapshot]:
        positions = self._client.get_all_positions()
        out: list[PositionSnapshot] = []
        for p in positions:
            out.append(
                PositionSnapshot(
                    symbol=str(p.symbol).upper(),
                    qty=float(p.qty),
                    market_value=float(p.market_value),
                )
            )
        return out

    def submit_notional_market_order(self, symbol: str, notional: float, side: str) -> str:
        if notional <= 0:
            raise ValueError("notional must be > 0")
        if side not in {"buy", "sell"}:
            raise ValueError("side must be 'buy' or 'sell'")
        req = MarketOrderRequest(
            symbol=symbol,
            notional=round(float(notional), 2),
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        order = self._client.submit_order(req)
        return str(order.id)

