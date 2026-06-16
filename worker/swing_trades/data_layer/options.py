"""Option catalog loader: keep the OPTIDX/OPTSTK rows of the Dhan instrument master and
build OptionContract records. Reuses instruments.parse_instrument_csv for the DataFrame.

Per Planning Pack/11_OPTIONS_MODULE.md (Phase O1). Index + stock options, both exchanges;
the volume > 1L enrollment filter (Phase O3) decides which ones are actually tracked."""
from __future__ import annotations

import datetime as _dt
from typing import Optional

import pandas as pd

from .models import OptionContract

# The two option instrument types we track: index options + stock options.
OPTION_INSTRUMENTS = {"OPTIDX", "OPTSTK"}


def _to_date(value) -> Optional[_dt.date]:
    s = str(value).strip()
    if not s:
        return None
    try:
        return _dt.date.fromisoformat(s[:10])  # master uses ISO YYYY-MM-DD
    except ValueError:
        return None


def _to_float(value) -> Optional[float]:
    try:
        s = str(value).strip()
        return float(s) if s else None
    except (ValueError, TypeError):
        return None


def _to_int(value) -> Optional[int]:
    try:
        s = str(value).strip()
        return int(float(s)) if s else None
    except (ValueError, TypeError):
        return None


def parse_option_contracts(df: pd.DataFrame) -> list[OptionContract]:
    """Keep OPTIDX/OPTSTK rows and build OptionContract records. Rows with a missing/garbled
    expiry, strike, or option type are skipped (we never store a half-formed contract)."""
    instr = df["INSTRUMENT"].str.strip().str.upper()
    sub = df[instr.isin(OPTION_INSTRUMENTS)]

    out: list[OptionContract] = []
    for rec in sub.to_dict("records"):
        expiry = _to_date(rec.get("SM_EXPIRY_DATE"))
        strike = _to_float(rec.get("STRIKE_PRICE"))
        option_type = str(rec.get("OPTION_TYPE", "")).strip().upper()
        if expiry is None or strike is None or option_type not in ("CE", "PE"):
            continue
        out.append(
            OptionContract(
                security_id=str(rec["SECURITY_ID"]).strip(),
                underlying_symbol=str(rec.get("UNDERLYING_SYMBOL", "")).strip(),
                underlying_security_id=(str(rec.get("UNDERLYING_SECURITY_ID", "")).strip() or None),
                exchange=str(rec.get("EXCH_ID", "")).strip().upper(),
                instrument_type=str(rec.get("INSTRUMENT", "")).strip().upper(),
                expiry_date=expiry,
                strike=strike,
                option_type=option_type,
                lot_size=_to_int(rec.get("LOT_SIZE")),
                display_name=(str(rec.get("DISPLAY_NAME", "")).strip() or None),
            )
        )
    return out
