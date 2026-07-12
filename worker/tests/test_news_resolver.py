"""Deterministic ISIN resolver: exact ISIN/scrip, exact + fuzzy name, and the reject-if-ambiguous
guarantees (a wrong ticker poisons a 100-day window; a miss only costs one observation)."""
from swing_trades.data_layer.models import UniverseInstrument
from swing_trades.data_layer.news.resolver import (
    InstrumentResolver,
    build_resolver_from_master,
    normalize_name,
)


def mk(isin, sec, exch, nsym, scrip, name, series="EQ"):
    return UniverseInstrument(
        isin=isin, security_id=sec, exchange_pref=exch, exchange_segment=f"{exch}_EQ",
        nse_symbol=nsym, bse_scrip_code=scrip, symbol_name=name,
        series=series, lot_size=1, asm_gsm_flag="N",
    )


UNI = [
    mk("INE002A01018", "2885", "NSE", "RELIANCE", "500325", "Reliance Industries"),
    mk("INE467B01029", "11536", "NSE", "TCS", "532540", "Tata Consultancy Services"),
    mk("INE714B01016", "500012", "BSE", "ANDHRAPET", "500012", "Andhra Petrochemicals", "X"),
    mk("INE715B01021", "3518", "NSE", "ANDHRSUGAR", "590062", "Andhra Sugars"),
    mk("INE111A01011", "111", "NSE", "ABCA", "590111", "ABC Limited"),   # normalizes to "ABC"
    mk("INE222A01012", "222", "NSE", "ABCB", "590222", "ABC Ltd"),       # also "ABC" -> ambiguous
]
R = InstrumentResolver(UNI)


def test_normalize_strips_suffix_and_leading_the():
    assert normalize_name("The Andhra Sugars Limited") == "ANDHRA SUGARS"
    assert normalize_name("Reliance Industries Ltd.") == "RELIANCE INDUSTRIES"


def test_resolve_by_isin_exact_and_case_insensitive():
    r = R.resolve(isin="ine002a01018")
    assert r.ok and r.method == "isin" and r.instrument.nse_symbol == "RELIANCE"


def test_resolve_by_bse_scrip_returns_nse_preferred():
    r = R.resolve(bse_scrip="500325")  # Reliance's BSE scrip -> NSE-preferred listing (Rule 4)
    assert r.ok and r.method == "bse_scrip"
    assert r.instrument.exchange_pref == "NSE" and r.instrument.isin == "INE002A01018"


def test_resolve_bse_only_by_scrip():
    r = R.resolve(bse_scrip="500012")  # Andhra Petrochemicals (BSE-only)
    assert r.ok and r.instrument.nse_symbol == "ANDHRAPET"


def test_resolve_by_exact_name():
    r = R.resolve(name="Reliance Industries Ltd")
    assert r.ok and r.method == "name_exact" and r.instrument.isin == "INE002A01018"


def test_resolve_by_fuzzy_name_subset():
    r = R.resolve(name="Tata Consultancy")  # subset -> token_set_ratio high, single ISIN
    assert r.ok and r.instrument.isin == "INE467B01029"


def test_isin_beats_a_mismatching_name():
    r = R.resolve(isin="INE002A01018", name="Totally Different Co")
    assert r.ok and r.instrument.isin == "INE002A01018"


def test_reject_ambiguous_exact_name():
    r = R.resolve(name="ABC Ltd")  # -> "ABC" maps to two different ISINs
    assert not r.ok and "ambiguous" in r.reason


def test_reject_low_confidence_name():
    r = R.resolve(name="Xyzzy Qwerty Fghij")
    assert not r.ok


def test_reject_when_no_identifier():
    assert not R.resolve().ok


def test_same_isin_name_variants_do_not_false_reject():
    # "RELIANCE" (ticker) and "RELIANCE INDUSTRIES" (name) both map to one ISIN; a fuzzy query that
    # sits between the two variants must still resolve, not reject for a small variant-to-variant margin.
    r = R.resolve(name="Reliance Industriess")  # typo -> not an exact key
    assert r.ok and r.instrument.isin == "INE002A01018"


def test_build_resolver_from_master_glues_to_the_instrument_parser():
    csv = (
        "SECURITY_ID,EXCH_ID,SEGMENT,ISIN,INSTRUMENT,UNDERLYING_SYMBOL,SYMBOL_NAME,DISPLAY_NAME,SERIES,LOT_SIZE,ASM_GSM_FLAG\n"
        "2885,NSE,E,INE002A01018,EQUITY,RELIANCE,RELIANCE INDUSTRIES LTD,Reliance Industries,EQ,1,N\n"
        "500325,BSE,E,INE002A01018,EQUITY,RELIANCE,RELIANCE INDUSTRIES LTD,Reliance Industries,A,1,N\n"
        "500012,BSE,E,INE714B01016,EQUITY,ANDHRAPET,ANDHRA PETROCHEMICALS,Andhra Petrochemicals,X,1,N\n"
    )
    res = build_resolver_from_master(csv)
    # dual-listed resolves NSE-preferred by BSE scrip; and an SME/illiquid BSE-only name is reachable
    assert res.resolve(bse_scrip="500325").instrument.exchange_pref == "NSE"
    assert res.resolve(bse_scrip="500012").instrument.nse_symbol == "ANDHRAPET"  # expand-on-the-fly reach
