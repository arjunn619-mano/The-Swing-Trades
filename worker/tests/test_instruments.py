import pytest

from swing_trades.data_layer import instruments as I

CSV = (
    "SECURITY_ID,EXCH_ID,SEGMENT,ISIN,INSTRUMENT,SYMBOL_NAME,SERIES,LOT_SIZE,ASM_GSM_FLAG\n"
    "2885,NSE,E,INE002A01018,EQUITY,RELIANCE,EQ,1,N\n"
    "500325,BSE,E,INE002A01018,EQUITY,RELIANCE,A,1,N\n"
    "1333,NSE,E,INE040A01034,EQUITY,HDFCBANK,EQ,1,N\n"
    "11536,NSE,E,INE467B01029,EQUITY,TCS,EQ,1,Y\n"
    "49081,NSE,D,INE467B01029,OPTIDX,TCS-FUT,,,N\n"
    "540001,BSE,E,INE999X01010,EQUITY,BSEONLY,A,1,N\n"
)


def test_equity_filter_excludes_derivatives():
    rows = I.equity_rows(I.parse_instrument_csv(CSV))
    assert all(r.segment == "E" for r in rows)
    assert len(rows) == 5  # 2 RELIANCE listings + HDFC + TCS(NSE) + BSEONLY; OPTIDX excluded


def test_resolve_prefers_nse_keeps_bse_scrip():
    uni = {u.isin: u for u in I.resolve_universe(I.equity_rows(I.parse_instrument_csv(CSV)))}
    rel = uni["INE002A01018"]
    assert rel.exchange_pref == "NSE"
    assert rel.exchange_segment == "NSE_EQ"
    assert rel.security_id == "2885"        # NSE id chosen to fetch with
    assert rel.bse_scrip_code == "500325"   # BSE scrip retained (Rule 4)
    assert rel.nse_symbol == "RELIANCE"


def test_resolve_bse_only_instrument():
    uni = {u.isin: u for u in I.resolve_universe(I.equity_rows(I.parse_instrument_csv(CSV)))}
    b = uni["INE999X01010"]
    assert b.exchange_pref == "BSE"
    assert b.exchange_segment == "BSE_EQ"
    assert b.bse_scrip_code == "540001"
    assert b.nse_symbol is None


def test_exclude_asm_gsm_flag():
    rows = I.equity_rows(I.parse_instrument_csv(CSV))
    uni = {u.isin: u for u in I.resolve_universe(rows, exclude_asm_gsm=True)}
    assert "INE467B01029" not in uni  # TCS flagged ASM/GSM = Y


def test_missing_columns_raise():
    with pytest.raises(ValueError):
        I.parse_instrument_csv("EXCH_ID,SEGMENT,ISIN\nNSE,E,INE1\n")
