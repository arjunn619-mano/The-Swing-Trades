"""Daily bulk market-quote: batch the universe (<=1000 ids/call) and parse the response.

Response shape: {"data": {"<SEGMENT>": {"<securityId>": {"ohlc": {...}, "volume": n, ...}}}}.
Only /marketfeed/quote (full mode) returns volume — /ohlc and /ltp do not (04_DHAN_INTEGRATION)."""
from __future__ import annotations

import datetime as _dt
from typing import Iterable

from .models import PriceBar, UniverseInstrument

MAX_INSTRUMENTS_PER_CALL = 1000


def _as_id(security_id: str):
    s = str(security_id).strip()
    return int(s) if s.isdigit() else s


def batch_instruments(
    universe: Iterable[UniverseInstrument],
    max_per_call: int = MAX_INSTRUMENTS_PER_CALL,
) -> list[dict[str, list]]:
    """Group security ids by exchange segment, split into request bodies of at most
    `max_per_call` ids total (Dhan allows up to 1000 instruments per request)."""
    batches: list[dict[str, list]] = []
    current: dict[str, list] = {}
    count = 0
    for inst in universe:
        if count >= max_per_call:
            batches.append(current)
            current, count = {}, 0
        current.setdefault(inst.exchange_segment, []).append(_as_id(inst.security_id))
        count += 1
    if current:
        batches.append(current)
    return batches


def parse_quote_response(payload: dict, trade_date: _dt.date) -> dict[str, PriceBar]:
    """Map {data: {SEGMENT: {securityId: {...}}}} to {security_id: PriceBar} for `trade_date`."""
    out: dict[str, PriceBar] = {}
    for _segment, instruments in (payload.get("data") or {}).items():
        for sec_id, q in instruments.items():
            ohlc = q.get("ohlc") or {}
            out[str(sec_id)] = PriceBar(
                trade_date=trade_date,
                open=float(ohlc.get("open", 0) or 0),
                high=float(ohlc.get("high", 0) or 0),
                low=float(ohlc.get("low", 0) or 0),
                close=float(ohlc.get("close", 0) or 0),
                volume=int(q.get("volume", 0) or 0),
            )
    return out
