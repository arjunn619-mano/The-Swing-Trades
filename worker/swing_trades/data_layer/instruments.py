"""Universe loader: download + parse the Dhan instrument master, filter to active NSE/BSE
equities, and resolve dual-listings by ISIN (Rule 4: NSE canonical, BSE scrip kept).

Columns are from the *detailed* master (api-scrip-master-detailed.csv). We validate the
expected columns are present and fail loudly on drift (Guardrail 10)."""
from __future__ import annotations

import io
from typing import Iterable, Optional

import pandas as pd

from .models import InstrumentRow, UniverseInstrument

INSTRUMENT_CSV_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"

# The security-id column name differs between the detailed/compact masters.
_SECURITY_ID_COLS = ("SECURITY_ID", "SEM_SMST_SECURITY_ID")
_REQUIRED_COLS = ("EXCH_ID", "SEGMENT", "ISIN", "INSTRUMENT", "SYMBOL_NAME")
_EQUITY_EXCHANGES = {"NSE", "BSE"}

# The Dhan "E" segment also contains Sovereign Gold Bonds (NSE SG), government securities
# and bonds (GS/GB/TB/G), fixed income (BSE F), SME (SM/NS) and ETFs (MF). Restricting to
# these series keeps the universe to liquid common equities (~3k instead of ~18k ISINs).
DEFAULT_ALLOWED_SERIES = {
    "NSE": {"EQ", "BE"},  # main board + trade-for-trade equities
    "BSE": {"A", "B"},    # main equity groups
}


def _find_security_id_col(columns: Iterable[str]) -> Optional[str]:
    cols = set(columns)
    return next((c for c in _SECURITY_ID_COLS if c in cols), None)


def _to_int(value) -> Optional[int]:
    try:
        s = str(value).strip()
        return int(float(s)) if s else None
    except (ValueError, TypeError):
        return None


def parse_instrument_csv(csv_text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(csv_text), dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    sec_col = _find_security_id_col(df.columns)
    missing = [c for c in _REQUIRED_COLS if c not in df.columns]
    if missing or sec_col is None:
        raise ValueError(
            f"Instrument CSV missing columns: {missing}"
            + ("" if sec_col else " and a SECURITY_ID column")
        )
    return df.rename(columns={sec_col: "SECURITY_ID"})


def equity_rows(
    df: pd.DataFrame,
    allowed_series: dict[str, set[str]] | None = None,
) -> list[InstrumentRow]:
    """Filter the master to active common equities. `allowed_series` maps exchange -> the
    set of SERIES codes to keep (defaults to liquid equity series); pass {} to keep all."""
    if allowed_series is None:
        allowed_series = DEFAULT_ALLOWED_SERIES

    seg = df["SEGMENT"].str.strip().str.upper()
    exch = df["EXCH_ID"].str.strip().str.upper()
    instr = df["INSTRUMENT"].str.strip().str.upper()
    isin = df["ISIN"].str.strip()

    mask = (
        (seg == "E")
        & exch.isin(_EQUITY_EXCHANGES)
        & (isin != "")
        & isin.str.upper().str.startswith("INE")  # equity ISINs are INE...; INF = mutual funds/ETFs
        & ((instr == "EQUITY") | (instr == ""))
    )

    if allowed_series and "SERIES" in df.columns:
        series = df["SERIES"].str.strip().str.upper()
        series_mask = pd.Series(False, index=df.index)
        for ex, codes in allowed_series.items():
            series_mask = series_mask | ((exch == ex) & series.isin(codes))
        mask = mask & series_mask

    rows: list[InstrumentRow] = []
    for rec in df[mask].to_dict("records"):
        rows.append(
            InstrumentRow(
                security_id=str(rec["SECURITY_ID"]).strip(),
                isin=str(rec["ISIN"]).strip(),
                exchange=str(rec["EXCH_ID"]).strip().upper(),
                segment="E",
                instrument=(str(rec["INSTRUMENT"]).strip().upper() or "EQUITY"),
                symbol_name=str(rec.get("SYMBOL_NAME", "")).strip(),
                series=(str(rec.get("SERIES", "")).strip() or None),
                lot_size=_to_int(rec.get("LOT_SIZE")),
                asm_gsm_flag=(str(rec.get("ASM_GSM_FLAG", "")).strip() or None),
            )
        )
    return rows


def resolve_universe(
    rows: Iterable[InstrumentRow],
    prefer_exchange: str = "NSE",
    exclude_asm_gsm: bool = False,
) -> list[UniverseInstrument]:
    by_isin: dict[str, dict[str, InstrumentRow]] = {}
    for r in rows:
        if exclude_asm_gsm and (r.asm_gsm_flag or "").upper() == "Y":
            continue
        by_isin.setdefault(r.isin, {})[r.exchange] = r

    universe: list[UniverseInstrument] = []
    for isin, listings in by_isin.items():
        nse = listings.get("NSE")
        bse = listings.get("BSE")
        chosen = nse if (prefer_exchange == "NSE" and nse) else (nse or bse)
        if chosen is None:
            continue
        universe.append(
            UniverseInstrument(
                isin=isin,
                security_id=chosen.security_id,
                exchange_pref=chosen.exchange,
                exchange_segment=f"{chosen.exchange}_EQ",
                nse_symbol=(nse.symbol_name if nse else None),
                bse_scrip_code=(bse.security_id if bse else None),
                symbol_name=chosen.symbol_name,
                series=chosen.series,
                lot_size=chosen.lot_size,
                asm_gsm_flag=chosen.asm_gsm_flag,
            )
        )
    return universe
