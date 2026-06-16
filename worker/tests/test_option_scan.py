import datetime as dt

import pytest

from swing_trades.pipeline.option_scan import OptionScanError, run_option_scan
from swing_trades.pipeline.option_store import FakeOptionStore, OptionContractRef

TRADE_DATE = dt.date(2025, 8, 18)   # Monday, a trading day
EXPIRY = dt.date(2025, 8, 28)       # last Thursday of Aug 2025

# Bulk-quote data keyed by the contract's own security_id (volume/OI/LTP).
QUOTES = {
    "911": {"ltp": 35.4, "volume": 250000, "oi": 120000},  # 1400 CE -> qualifies (>1L)
    "912": {"ltp": 33.0, "volume": 80000, "oi": 90000},    # 1400 PE -> below 1L
    "913": {"ltp": 0.0, "volume": 0, "oi": 0},             # 1420 CE -> dead
    "914": {"ltp": 48.0, "volume": 120000, "oi": 50000},   # 1420 PE -> qualifies (>1L)
}

# Option chain for IV/Greeks enrichment of the qualifying RELIANCE strikes.
CHAIN = {
    "status": "success",
    "data": {
        "last_price": 1402.5,
        "oc": {
            "1400.000000": {
                "ce": {"greeks": {"delta": 0.52, "theta": -1.2, "gamma": 0.003, "vega": 4.1},
                       "implied_volatility": 18.5, "last_price": 35.4, "oi": 120000,
                       "previous_oi": 100000, "volume": 250000},
                "pe": {"greeks": {"delta": -0.48}, "implied_volatility": 19.2, "last_price": 33.0,
                       "oi": 90000, "previous_oi": 95000, "volume": 80000},
            },
            "1420.000000": {
                "ce": {"greeks": {}, "implied_volatility": 0, "last_price": 0, "oi": 0,
                       "previous_oi": 0, "volume": 0},
                "pe": {"greeks": {"delta": -0.6}, "implied_volatility": 20.0, "last_price": 48.0,
                       "oi": 50000, "previous_oi": 40000, "volume": 120000},
            },
        },
    },
}


class FakeClient:
    def __init__(self, quotes_by_secid, chains, fail_chain_scrips=()):
        self.quotes = quotes_by_secid
        self.chains = chains
        self.fail_chain_scrips = set(fail_chain_scrips)
        self.quote_calls = []
        self.chain_calls = []

    def quote(self, batch):
        self.quote_calls.append(batch)
        data: dict = {}
        for seg, ids in batch.items():
            data.setdefault(seg, {})
            for sid in ids:
                key = str(sid)
                qd = self.quotes.get(key)
                if qd is not None:
                    data[seg][key] = {
                        "last_price": qd["ltp"], "ohlc": {"open": 0, "high": 0, "low": 0, "close": qd["ltp"]},
                        "volume": qd["volume"], "oi": qd["oi"],
                    }
        return {"data": data, "status": "success"}

    def option_chain(self, scrip, seg, expiry):
        self.chain_calls.append((scrip, seg, expiry))
        if scrip in self.fail_chain_scrips:
            raise RuntimeError("HTTP 400 :: Invalid SecurityId")
        return self.chains.get((scrip, seg, expiry), {"data": {"oc": {}}})


def _ref(cid, secid, strike, opt_type):
    return OptionContractRef(
        id=cid, security_id=secid, underlying_symbol="RELIANCE", underlying_security_id="2885",
        exchange="NSE", instrument_type="OPTSTK", expiry_date=EXPIRY, strike=strike,
        option_type=opt_type, lot_size=500,
    )


def _store():
    store = FakeOptionStore()
    store.add_contract(_ref(11, "911", 1400.0, "CE"))
    store.add_contract(_ref(12, "912", 1400.0, "PE"))
    store.add_contract(_ref(13, "913", 1420.0, "CE"))
    store.add_contract(_ref(14, "914", 1420.0, "PE"))
    return store


def _client(**kw):
    return FakeClient(QUOTES, {(2885, "NSE_EQ", "2025-08-28"): CHAIN}, **kw)


def _run(store, client):
    return run_option_scan(TRADE_DATE, store=store, dhan_client=client,
                           volume_threshold=100_000, quote_interval=0, request_interval=0,
                           sleep=lambda _s: None)


def test_enrolls_only_contracts_over_volume_threshold():
    store, client = _store(), _client()
    summary = _run(store, client)

    assert summary.status == "success"
    assert summary.contracts_seen == 4            # all four quoted
    assert summary.qualifying == 2                # 911 (250k) + 914 (120k)
    assert summary.enrolled == 2
    assert store.count_tracked() == 2
    assert 11 in store.tracker and 14 in store.tracker
    assert 12 not in store.tracker and 13 not in store.tracker


def test_entry_locked_and_greeks_enriched():
    store, client = _store(), _client()
    _run(store, client)

    assert store.tracker[11]["entry_ltp"] == 35.4
    assert store.tracker[11]["entry_iv"] == 18.5     # from the chain enrichment
    assert len(client.chain_calls) == 1              # one enrichment call for RELIANCE
    obs = store.observations[(11, TRADE_DATE)]
    assert obs["return_vs_entry"] == 0.0
    assert obs["days_to_expiry"] == 10
    assert obs["delta"] == 0.52 and obs["iv"] == 18.5
    assert abs(obs["oi_change_pct"] - 0.2) < 1e-9


def test_chain_enrich_failure_is_isolated():
    store = _store()
    client = _client(fail_chain_scrips={2885})       # chain 400s (like the index id bug)
    summary = _run(store, client)

    assert summary.status == "success"               # quote-driven tracking still works
    assert summary.enrolled == 2                      # enrolled from quoted volume
    assert summary.errors >= 1
    assert store.observations[(11, TRADE_DATE)]["iv"] is None  # no Greeks, but tracked


class RateLimitedClient:
    def __init__(self):
        self.calls = 0

    def quote(self, batch):
        self.calls += 1
        raise RuntimeError("429 Client Error: Too Many Requests :: {\"805\":\"Too many requests\"}")


def test_quote_rate_limit_aborts_fast():
    store = FakeOptionStore()
    for i in range(2001):  # 2001 contracts -> 3 quote batches (1000/call)
        store.add_contract(_ref(1000 + i, str(10000 + i), 100.0 + i, "CE"))
    client = RateLimitedClient()
    with pytest.raises(OptionScanError):
        run_option_scan(TRADE_DATE, store=store, dhan_client=client, quote_interval=0,
                        request_interval=0, rate_limit_cooldown=0, max_consecutive_rate_limits=3,
                        sleep=lambda _s: None)
    # circuit-breaker: aborted after 3 consecutive 429s instead of hammering all ~3 batches
    assert client.calls == 3
    assert store.count_tracked() == 0   # nothing enrolled on a rate-limited run


def test_expired_contract_is_deleted():
    store, client = _store(), _client()
    store.enroll_option(99, dt.date(2025, 7, 20), 12.0, 15.0, 1000, dt.date(2025, 8, 15))
    summary = _run(store, client)

    assert summary.expired == 1
    assert 99 not in store.tracker
    assert store.count_tracked() == 2


def test_rerun_same_day_is_idempotent():
    store, client = _store(), _client()
    _run(store, client)
    after_first = store.count_tracked()

    summary2 = _run(store, client)
    assert summary2.enrolled == 0
    assert store.count_tracked() == after_first
    assert store.observations[(14, TRADE_DATE)]["return_vs_entry"] == 0.0


def test_full_snapshot_handed_to_sink():
    store, client = _store(), _client()
    captured = {}

    def sink(rows, trade_date):
        captured["rows"] = rows
        captured["date"] = trade_date

    run_option_scan(TRADE_DATE, store=store, dhan_client=client, quote_interval=0,
                    request_interval=0, sleep=lambda _s: None, snapshot_sink=sink)
    assert captured["date"] == TRADE_DATE
    assert len(captured["rows"]) == 4                 # every quoted contract, incl. the dead one
    assert any(r["volume"] == 0 for r in captured["rows"])


def test_non_trading_day_writes_nothing():
    store = _store()
    summary = run_option_scan(dt.date(2025, 8, 17), store=store, dhan_client=_client(),
                              quote_interval=0, request_interval=0, sleep=lambda _s: None)
    assert summary.status == "skipped_non_trading_day"
    assert store.count_tracked() == 0
