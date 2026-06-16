"""Dataclasses shared across the Dhan data layer."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TokenInfo:
    access_token: str
    expiry_time: Optional[str] = None
    client_id: Optional[str] = None


@dataclass(frozen=True)
class InstrumentRow:
    """One raw listing row from the instrument master (a single exchange listing)."""

    security_id: str
    isin: str
    exchange: str  # NSE | BSE
    segment: str  # E (equity)
    instrument: str  # EQUITY
    symbol_name: str  # long legal name, e.g. RELIANCE INDUSTRIES LTD
    series: Optional[str] = None
    lot_size: Optional[int] = None
    asm_gsm_flag: Optional[str] = None
    trading_symbol: Optional[str] = None  # the ticker, e.g. RELIANCE (UNDERLYING_SYMBOL)
    display_name: Optional[str] = None  # nice name, e.g. Reliance Industries (DISPLAY_NAME)


@dataclass(frozen=True)
class UniverseInstrument:
    """A resolved, per-ISIN instrument after dual-listing resolution (Rule 4: NSE preferred,
    BSE scrip kept for reference)."""

    isin: str
    security_id: str  # the id we fetch with (NSE's if available, else BSE's)
    exchange_pref: str  # NSE | BSE
    exchange_segment: str  # NSE_EQ | BSE_EQ
    nse_symbol: Optional[str]
    bse_scrip_code: Optional[str]
    symbol_name: str
    series: Optional[str]
    lot_size: Optional[int]
    asm_gsm_flag: Optional[str]


@dataclass(frozen=True)
class PriceBar:
    trade_date: _dt.date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class OptionContract:
    """One option contract (index or stock) from the instrument master.
    Planning Pack/11_OPTIONS_MODULE.md (Phase O1)."""

    security_id: str
    underlying_symbol: str            # e.g. RELIANCE, NIFTY
    underlying_security_id: Optional[str]
    exchange: str                     # NSE | BSE
    instrument_type: str              # OPTIDX | OPTSTK
    expiry_date: _dt.date
    strike: float
    option_type: str                  # CE | PE
    lot_size: Optional[int] = None
    display_name: Optional[str] = None


@dataclass(frozen=True)
class OptionQuote:
    """One side (CE or PE) of one strike from an /optionchain snapshot (Phase O2)."""

    strike: float
    option_type: str                  # CE | PE
    last_price: float                 # premium LTP
    oi: int
    previous_oi: int
    volume: int
    implied_volatility: Optional[float] = None
    delta: Optional[float] = None
    theta: Optional[float] = None
    gamma: Optional[float] = None
    vega: Optional[float] = None
    previous_close: Optional[float] = None

    @property
    def oi_change_pct(self) -> Optional[float]:
        if self.previous_oi:
            return (self.oi - self.previous_oi) / self.previous_oi
        return None


@dataclass(frozen=True)
class OptionChainSnapshot:
    """A parsed /optionchain response for one (underlying, expiry)."""

    expiry: str                       # YYYY-MM-DD
    underlying_last_price: Optional[float]
    quotes: list["OptionQuote"]
    underlying_scrip: Optional[int] = None
    underlying_seg: Optional[str] = None
