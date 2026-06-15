import pytest

from swing_trades.data_layer import instruments as I

CSV = (
    "SECURITY_ID,EXCH_ID,SEGMENT,ISIN,INSTRUMENT,UNDERLYING_SYMBOL,SYMBOL_NAME,DISPLAY_NAME,SERIES,LOT_SIZE,ASM_GSM_FLAG\n"
    "2885,NSE,E,INE002A01018,EQUITY,RELIANCE,RELIANCE INDUSTRIES LTD,Reliance Industries,EQ,1,N\n"
    "500325,BSE,E,INE002A01018,EQUITY,RELIANCE,RELIANCE INDUSTRIES LTD,Reliance Industries,A,1,N\n"
    "1333,NSE,E,INE040A01034,EQUITY,HDFCBANK,HDFC BANK LTD,HDFC Bank,EQ,1,N\n"
    "11536,NSE,E,INE467B01029,EQUITY,TCS,TATA CONSULTANCY SERV LT,Tata Consultancy Services,EQ,1,Y\n"
    "49081,NSE,D,INE467B01029,OPTIDX,TCS,TCS FUT,TCS Fut,,,\n"
    "540001,BSE,E,INE999X01010,EQUITY,BSEONLY,BSEONLY LIMITED,BSEonly,A,1,N\n"
    "1199,NSE,E,INE777Z01011,EQUITY,SGBTEST,SGB TEST,SGB Test,SG,1,N\n"      # SGB -> excluded (series)
    "540999,BSE,E,INE888Z01022,EQUITY,BONDTEST,BOND TEST,Bond Test,F,1,N\n"  # BSE F (debt) -> excluded (series)
    "538591,BSE,E,INF204KA1RY0,EQUITY,FUNDX,FUND X,Fund X,A,1,N\n"           # INF = mutual fund -> excluded (ISIN)
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
    assert rel.nse_symbol == "RELIANCE"     # ticker from UNDERLYING_SYMBOL
    assert rel.symbol_name == "Reliance Industries"  # nice name from DISPLAY_NAME


def test_resolve_bse_only_instrument():
    uni = {u.isin: u for u in I.resolve_universe(I.equity_rows(I.parse_instrument_csv(CSV)))}
    b = uni["INE999X01010"]
    assert b.exchange_pref == "BSE"
    assert b.exchange_segment == "BSE_EQ"
    assert b.bse_scrip_code == "540001"
    assert b.nse_symbol == "BSEONLY"  # ticker for the chosen (BSE) listing


def test_exclude_asm_gsm_flag():
    rows = I.equity_rows(I.parse_instrument_csv(CSV))
    uni = {u.isin: u for u in I.resolve_universe(rows, exclude_asm_gsm=True)}
    assert "INE467B01029" not in uni  # TCS flagged ASM/GSM = Y


def test_excludes_non_equity_series_and_funds():
    uni = {u.isin for u in I.resolve_universe(I.equity_rows(I.parse_instrument_csv(CSV)))}
    assert "INE777Z01011" not in uni  # Sovereign Gold Bond (NSE SG series)
    assert "INE888Z01022" not in uni  # BSE F group (debt)
    assert "INF204KA1RY0" not in uni  # mutual fund (INF ISIN prefix)


def test_empty_allowed_series_keeps_all():
    isins = {r.isin for r in I.equity_rows(I.parse_instrument_csv(CSV), allowed_series={})}
    assert "INE777Z01011" in isins  # no series filter -> SGB kept


def test_missing_columns_raise():
    with pytest.raises(ValueError):
        I.parse_instrument_csv("EXCH_ID,SEGMENT,ISIN\nNSE,E,INE1\n")
