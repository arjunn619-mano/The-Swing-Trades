"""Parse Dhan /optionchain responses and map a contract to its (UnderlyingScrip, UnderlyingSeg).

The chain is the single EOD source (Planning Pack 11): one call per (underlying, expiry)
returns every strike's CE/PE with LTP, OI, volume, IV and Greeks, plus the underlying LTP.
Pair with DhanDataClient.option_chain (raw), like quotes.parse_quote_response."""
from __future__ import annotations

from typing import Optional

from .models import OptionChainSnapshot, OptionContract, OptionQuote


def _f(v) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def _i(v) -> int:
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def _of(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def parse_option_chain(
    payload: dict,
    expiry: str,
    underlying_scrip: Optional[int] = None,
    underlying_seg: Optional[str] = None,
) -> OptionChainSnapshot:
    """Map {data: {last_price, oc: {strike: {ce, pe}}}} to an OptionChainSnapshot.
    Empty/illiquid sides are kept (all zeros) — the volume > 1L filter runs in the scan."""
    data = payload.get("data") or {}
    oc = data.get("oc") or {}
    quotes: list[OptionQuote] = []
    for strike_str, sides in oc.items():
        try:
            strike = float(strike_str)
        except (ValueError, TypeError):
            continue
        sides = sides or {}
        for side_key, opt_type in (("ce", "CE"), ("pe", "PE")):
            side = sides.get(side_key)
            if not side:
                continue
            greeks = side.get("greeks") or {}
            quotes.append(
                OptionQuote(
                    strike=strike,
                    option_type=opt_type,
                    last_price=_f(side.get("last_price")),
                    oi=_i(side.get("oi")),
                    previous_oi=_i(side.get("previous_oi")),
                    volume=_i(side.get("volume")),
                    implied_volatility=_of(side.get("implied_volatility")),
                    delta=_of(greeks.get("delta")),
                    theta=_of(greeks.get("theta")),
                    gamma=_of(greeks.get("gamma")),
                    vega=_of(greeks.get("vega")),
                    previous_close=_of(side.get("previous_close_price")),
                )
            )
    return OptionChainSnapshot(
        expiry=expiry,
        underlying_last_price=_of(data.get("last_price")),
        quotes=quotes,
        underlying_scrip=underlying_scrip,
        underlying_seg=underlying_seg,
    )


def underlying_ref(contract: OptionContract) -> tuple[int, str]:
    """Map a contract to the (UnderlyingScrip, UnderlyingSeg) the option-chain API expects.
    Index options → the index itself (IDX_I); stock options → the underlying equity (NSE_EQ).
    The exact index segment is verified on the first live snapshot (Planning Pack 11 open items)."""
    if contract.instrument_type == "OPTIDX":
        seg = "IDX_I"
    else:
        seg = f"{contract.exchange}_EQ"
    sid = contract.underlying_security_id or ""
    scrip = int(sid) if sid.isdigit() else 0
    return scrip, seg
