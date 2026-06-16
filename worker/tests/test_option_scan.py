import datetime as dt

from swing_trades.pipeline.option_scan import run_option_scan
from swing_trades.pipeline.option_store import FakeOptionStore, OptionContractRef

TRADE_DATE = dt.date(2025, 8, 18)   # Monday, a trading day
EXPIRY = dt.date(2025, 8, 28)       # last Thursday of Aug 2025

CHAIN = {
    "status": "success",
    "data": {
        "last_price": 1402.5,
        "oc": {
            "1400.000000": {
                "ce": {"greeks": {"delta": 0.52, "theta": -1.2, "gamma": 0.003, "vega": 4.1},
                       "implied_volatility": 18.5, "last_price": 35.4, "oi": 120000,
                       "previous_oi": 100000, "previous_close_price": 30.0, "volume": 250000},
                "pe": {"greeks": {"delta": -0.48}, "implied_volatility": 19.2, "last_price": 33.0,
                       "oi": 90000, "previous_oi": 95000, "volume": 80000},   # vol < 1L -> no enroll
            },
            "1420.000000": {
                "ce": {"greeks": {}, "implied_volatility": 0, "last_price": 0, "oi": 0,
                       "previous_oi": 0, "volume": 0},                         # dead -> no enroll
                "pe": {"greeks": {"delta": -0.6}, "implied_volatility": 20.0, "last_price": 48.0,
                       "oi": 50000, "previous_oi": 40000, "volume": 120000},   # vol > 1L -> enroll
            },
        },
    },
}


class FakeChainClient:
    def __init__(self, chains):
        self.chains = chains
        self.calls = []

    def option_chain(self, scrip, seg, expiry):
        self.calls.append((scrip, seg, expiry))
        return self.chains.get((scrip, seg, expiry), {"data": {"oc": {}}})


def _ref(cid, strike, opt_type):
    return OptionContractRef(
        id=cid, security_id=str(900 + cid), underlying_symbol="RELIANCE",
        underlying_security_id="2885", exchange="NSE", instrument_type="OPTSTK",
        expiry_date=EXPIRY, strike=strike, option_type=opt_type, lot_size=500,
    )


def _store():
    store = FakeOptionStore()
    store.add_contract(_ref(11, 1400.0, "CE"))
    store.add_contract(_ref(12, 1400.0, "PE"))
    store.add_contract(_ref(13, 1420.0, "CE"))
    store.add_contract(_ref(14, 1420.0, "PE"))
    return store


def _client():
    return FakeChainClient({(2885, "NSE_EQ", "2025-08-28"): CHAIN})


def _run(store, client):
    return run_option_scan(TRADE_DATE, store=store, dhan_client=client,
                           volume_threshold=100_000, sleep=lambda _s: None)


def test_enrolls_only_contracts_over_volume_threshold():
    store, client = _store(), _client()
    summary = _run(store, client)

    assert summary.status == "success"
    assert summary.chains_fetched == 1
    assert summary.contracts_seen == 4
    assert summary.qualifying == 2          # 1400 CE (250k) + 1420 PE (120k)
    assert summary.enrolled == 2
    assert store.count_tracked() == 2
    assert 11 in store.tracker and 14 in store.tracker   # the two that cleared 1L
    assert 12 not in store.tracker and 13 not in store.tracker


def test_entry_locked_and_day0_observation():
    store, client = _store(), _client()
    _run(store, client)

    assert store.tracker[11]["entry_ltp"] == 35.4
    assert store.tracker[11]["entry_iv"] == 18.5
    obs = store.observations[(11, TRADE_DATE)]
    assert obs["return_vs_entry"] == 0.0           # day 0: ltp == entry
    assert obs["days_to_expiry"] == 10             # 2025-08-28 - 2025-08-18
    assert obs["delta"] == 0.52
    assert abs(obs["oi_change_pct"] - 0.2) < 1e-9  # (120000-100000)/100000


def test_expired_contract_is_deleted():
    store, client = _store(), _client()
    # a contract enrolled earlier whose expiry has now passed
    store.enroll_option(99, dt.date(2025, 7, 20), 12.0, 15.0, 1000, dt.date(2025, 8, 15))
    summary = _run(store, client)

    assert summary.expired == 1
    assert 99 not in store.tracker                 # deleted (history lives in the Parquet archive)
    assert store.count_tracked() == 2              # only the two fresh enrolments remain


def test_rerun_same_day_is_idempotent():
    store, client = _store(), _client()
    _run(store, client)
    tracked_after_first = store.count_tracked()

    summary2 = _run(store, client)
    assert summary2.enrolled == 0                  # both already tracked
    assert store.count_tracked() == tracked_after_first
    assert store.observations[(14, TRADE_DATE)]["return_vs_entry"] == 0.0


def test_full_snapshot_handed_to_sink():
    store, client = _store(), _client()
    captured = {}

    def sink(rows, trade_date):
        captured["rows"] = rows
        captured["date"] = trade_date

    run_option_scan(TRADE_DATE, store=store, dhan_client=client, sleep=lambda _s: None,
                    snapshot_sink=sink)
    assert captured["date"] == TRADE_DATE
    assert len(captured["rows"]) == 4              # every strike/side, incl. the dead 1420 CE
    assert any(r["volume"] == 0 for r in captured["rows"])  # dead strike kept for the archive


class FlakyChainClient:
    """Serves CHAIN for the RELIANCE key; raises for any underlying in `fail_scrips`."""

    def __init__(self, chains, fail_scrips=()):
        self.chains = chains
        self.fail_scrips = set(fail_scrips)
        self.calls = []

    def option_chain(self, scrip, seg, expiry):
        self.calls.append((scrip, seg, expiry))
        if scrip in self.fail_scrips:
            raise RuntimeError("HTTP 400 :: simulated bad request")
        return self.chains.get((scrip, seg, expiry), {"data": {"oc": {}}})


def test_chain_error_is_isolated_not_fatal():
    store = _store()
    # a second underlying (TCS) whose chain call will fail
    store.add_contract(OptionContractRef(
        id=21, security_id="2100", underlying_symbol="TCS", underlying_security_id="11536",
        exchange="NSE", instrument_type="OPTSTK", expiry_date=EXPIRY, strike=3500.0,
        option_type="CE", lot_size=175,
    ))
    client = FlakyChainClient({(2885, "NSE_EQ", "2025-08-28"): CHAIN}, fail_scrips={11536})
    summary = run_option_scan(TRADE_DATE, store=store, dhan_client=client,
                              volume_threshold=100_000, sleep=lambda _s: None)
    assert summary.status == "success"     # the bad underlying did not kill the run
    assert summary.errors >= 1
    assert summary.sample_errors           # captured the reason for the artifact
    assert summary.enrolled == 2           # RELIANCE 1400 CE + 1420 PE still enrolled


def test_non_trading_day_writes_nothing():
    store = _store()
    summary = run_option_scan(dt.date(2025, 8, 17), store=store, dhan_client=_client(),
                              sleep=lambda _s: None)
    assert summary.status == "skipped_non_trading_day"
    assert store.count_tracked() == 0
