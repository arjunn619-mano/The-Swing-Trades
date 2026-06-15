"""Parse the Dhan daily historical-data response (columnar parallel arrays)."""
from __future__ import annotations

from ..utils.timeutils import epoch_to_ist_date
from .models import PriceBar

_ARRAYS = ("open", "high", "low", "close", "volume", "timestamp")


def parse_historical_response(payload: dict) -> list[PriceBar]:
    """Convert {open[], high[], low[], close[], volume[], timestamp[]} into PriceBars.
    An empty/over-range response ({}) yields []. Length mismatch fails loudly (Guardrail 10)."""
    if not payload:
        return []
    missing = [k for k in _ARRAYS if k not in payload]
    if missing:
        raise ValueError(f"Historical response missing arrays: {missing}")

    o, h, low, c, v, ts = (payload[k] for k in _ARRAYS)
    n = len(o)
    if any(len(arr) != n for arr in (h, low, c, v, ts)):
        raise ValueError("Historical response arrays have mismatched lengths")

    bars: list[PriceBar] = []
    for i in range(n):
        bars.append(
            PriceBar(
                trade_date=epoch_to_ist_date(ts[i]),
                open=float(o[i]),
                high=float(h[i]),
                low=float(low[i]),
                close=float(c[i]),
                volume=int(v[i]),
            )
        )
    return bars
