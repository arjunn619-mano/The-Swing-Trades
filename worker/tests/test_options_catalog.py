import datetime as dt

from swing_trades.data_layer.instruments import parse_instrument_csv
from swing_trades.data_layer.options import parse_option_contracts

CSV = (
    "SECURITY_ID,EXCH_ID,SEGMENT,ISIN,INSTRUMENT,UNDERLYING_SYMBOL,UNDERLYING_SECURITY_ID,"
    "SYMBOL_NAME,DISPLAY_NAME,SM_EXPIRY_DATE,STRIKE_PRICE,OPTION_TYPE,SERIES,LOT_SIZE,ASM_GSM_FLAG\n"
    # index options (NIFTY) — CE + PE
    "35022,NSE,D,,OPTIDX,NIFTY,26000,NIFTY,NIFTY 28 JUL 29300 CALL,2026-07-28,29300.00000,CE,,75,\n"
    "35023,NSE,D,,OPTIDX,NIFTY,26000,NIFTY,NIFTY 28 JUL 29300 PUT,2026-07-28,29300.00000,PE,,75,\n"
    # stock option (RELIANCE)
    "538591,NSE,D,,OPTSTK,RELIANCE,2885,RELIANCE,RELIANCE 31 JUL 1400 CALL,2026-07-31,1400.00000,CE,,500,\n"
    # BSE index option (SENSEX)
    "843000,BSE,D,,OPTIDX,SENSEX,1,SENSEX,SENSEX 30 JUN 80000 PUT,2026-06-30,80000.00000,PE,,10,\n"
    # equity row — excluded (not an option)
    "2885,NSE,E,INE002A01018,EQUITY,RELIANCE,2885,RELIANCE INDUSTRIES LTD,Reliance Industries,,,,EQ,1,N\n"
    # stock future — excluded (FUTSTK / no option type)
    "49999,NSE,D,,FUTSTK,RELIANCE,2885,RELIANCE,RELIANCE 31 JUL FUT,2026-07-31,0,,,500,\n"
    # malformed option (no expiry) — skipped
    "60000,NSE,D,,OPTSTK,TCS,11536,TCS,TCS BAD,,3500.00000,CE,,175,\n"
)


def _by_key(csv=CSV):
    return {
        (o.underlying_symbol, o.option_type, o.exchange): o
        for o in parse_option_contracts(parse_instrument_csv(csv))
    }


def test_keeps_only_well_formed_options():
    opts = parse_option_contracts(parse_instrument_csv(CSV))
    # 2 NIFTY + 1 RELIANCE + 1 SENSEX = 4; equity/future/malformed excluded
    assert len(opts) == 4
    assert all(o.option_type in ("CE", "PE") for o in opts)
    assert all(o.instrument_type in ("OPTIDX", "OPTSTK") for o in opts)


def test_index_and_stock_both_present():
    types = {o.instrument_type for o in parse_option_contracts(parse_instrument_csv(CSV))}
    assert types == {"OPTIDX", "OPTSTK"}


def test_option_fields_parsed():
    ce = _by_key()[("NIFTY", "CE", "NSE")]
    assert ce.strike == 29300.0
    assert ce.expiry_date == dt.date(2026, 7, 28)
    assert ce.lot_size == 75
    assert ce.underlying_security_id == "26000"
    assert ce.display_name == "NIFTY 28 JUL 29300 CALL"


def test_bse_index_option_kept():
    sensex = _by_key()[("SENSEX", "PE", "BSE")]
    assert sensex.exchange == "BSE"
    assert sensex.instrument_type == "OPTIDX"
    assert sensex.expiry_date == dt.date(2026, 6, 30)


def test_malformed_option_skipped():
    ids = {o.security_id for o in parse_option_contracts(parse_instrument_csv(CSV))}
    assert "60000" not in ids  # missing expiry -> skipped
