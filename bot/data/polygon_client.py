from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import time

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


@dataclass
class PolygonClient:
    api_key: str
    base_url: str = "https://api.polygon.io"
    last_five_reqs: list[float] = field(default_factory=list)  # mutable default safely

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(multiplier=2, min=12, max=60),
        retry=retry_if_exception_type(requests.exceptions.HTTPError),
    )
    def _get_json(self, path: str, params: dict[str, str]) -> dict:
        # --- Enforce 5 requests per minute ---
        if len(self.last_five_reqs) >= 5:
            elapsed = time.time() - self.last_five_reqs[0]
            if elapsed < 60:
                time.sleep(60 - elapsed)
            self.last_five_reqs.pop(0)

        self.last_five_reqs.append(time.time())

        # Make the request
        p = dict(params)
        p["apiKey"] = self.api_key
        url = f"{self.base_url}{path}"
        resp = requests.get(url, params=p, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def get_last_two_daily_closes(self, symbol: str, session_date: date) -> tuple[float, float]:
        """
        Returns (close, prev_close) for `session_date` using Polygon aggregates.

        Note: for real trading you may want more robust “latest available session”
        logic; this keeps the interface simple.
        """
        sym = symbol.upper()
        d_to = session_date.isoformat()
        # Minimal lookback window to capture the previous trading day too.
        d_from = (session_date - timedelta(days=14)).isoformat()

        data = self._get_json(
            f"/v2/aggs/ticker/{sym}/range/1/day/{d_from}/{d_to}",
            params={"adjusted": "true", "sort": "desc", "limit": "10"},
        )
        results = data.get("results") or []
        if len(results) < 2:
            raise RuntimeError(f"Polygon did not return 2 daily bars for {sym} up to {d_to}")
        return float(results[0]["c"]), float(results[1]["c"])

    def get_recent_daily_closes(self, symbol: str, session_date: date, *, lookback_days: int) -> list[float]:
        """
        Returns a list of closes (most-recent first) for up to `lookback_days` trading days
        ending at `session_date`.
        """
        if lookback_days <= 1:
            raise ValueError("lookback_days must be > 1")
        sym = symbol.upper()
        d_to = session_date.isoformat()
        d_from = (session_date - timedelta(days=max(14, lookback_days * 3))).isoformat()

        data = self._get_json(
            f"/v2/aggs/ticker/{sym}/range/1/day/{d_from}/{d_to}",
            params={"adjusted": "true", "sort": "desc", "limit": str(min(50000, lookback_days + 25))},
        )
        results = data.get("results") or []
        closes = [float(r["c"]) for r in results]
        if len(closes) < 2:
            raise RuntimeError(f"Polygon did not return enough daily bars for {sym} up to {d_to}")
        return closes[:lookback_days]

