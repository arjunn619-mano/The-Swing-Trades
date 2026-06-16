import datetime as dt

import pandas as pd

from swing_trades.archive.options_archive import (
    ARCHIVE_COLUMNS,
    make_archive_sink,
    snapshot_filename,
    upload_to_release,
    write_snapshot_parquet,
)

TRADE_DATE = dt.date(2025, 8, 18)


def _row(strike, opt_type, volume):
    return {
        "trade_date": TRADE_DATE.isoformat(), "security_id": "911", "underlying_symbol": "RELIANCE",
        "instrument_type": "OPTSTK", "exchange": "NSE", "expiry_date": "2025-08-28",
        "strike": strike, "option_type": opt_type, "lot_size": 500, "ltp": 35.4, "volume": volume,
        "oi": 120000, "previous_oi": 100000, "oi_change_pct": 0.2, "iv": 18.5, "delta": 0.52,
        "theta": -1.2, "gamma": 0.003, "vega": 4.1, "underlying_last": 1402.5, "days_to_expiry": 10,
    }


def test_write_and_read_back(tmp_path):
    rows = [_row(1400.0, "CE", 250000), _row(1420.0, "PE", 120000)]
    path = write_snapshot_parquet(rows, TRADE_DATE, tmp_path)
    assert path.name == "options_2025-08-18.parquet"
    df = pd.read_parquet(path)
    assert list(df.columns) == ARCHIVE_COLUMNS
    assert len(df) == 2
    assert set(df["option_type"]) == {"CE", "PE"}
    assert df["volume"].max() == 250000


def test_empty_snapshot_still_writes_file(tmp_path):
    path = write_snapshot_parquet([], TRADE_DATE, tmp_path)
    assert path.exists()
    df = pd.read_parquet(path)
    assert len(df) == 0
    assert list(df.columns) == ARCHIVE_COLUMNS


def test_snapshot_filename():
    assert snapshot_filename(TRADE_DATE) == "options_2025-08-18.parquet"


class _Result:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


class _FakeRunner:
    def __init__(self, results=None):
        self.calls = []
        self.results = results or {}

    def __call__(self, cmd):
        self.calls.append(cmd)
        sub = cmd[2] if len(cmd) > 2 else ""
        return self.results.get(sub, _Result(0))


def _subcommands(runner):
    return [c[2] for c in runner.calls]


def test_upload_creates_release_when_missing(tmp_path):
    path = write_snapshot_parquet([_row(1400.0, "CE", 250000)], TRADE_DATE, tmp_path)
    runner = _FakeRunner({"view": _Result(1)})  # release does not exist yet
    upload_to_release(path, runner=runner)
    assert _subcommands(runner) == ["view", "create", "upload"]
    assert "--clobber" in runner.calls[-1]


def test_upload_skips_create_when_release_exists(tmp_path):
    path = write_snapshot_parquet([_row(1400.0, "CE", 250000)], TRADE_DATE, tmp_path)
    runner = _FakeRunner({"view": _Result(0)})  # release already exists
    upload_to_release(path, runner=runner)
    assert _subcommands(runner) == ["view", "upload"]


def test_upload_raises_on_failure(tmp_path):
    path = write_snapshot_parquet([_row(1400.0, "CE", 250000)], TRADE_DATE, tmp_path)
    runner = _FakeRunner({"view": _Result(0), "upload": _Result(1, stderr="boom")})
    try:
        upload_to_release(path, runner=runner)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "boom" in str(e)


def test_archive_sink_writes_and_uploads(tmp_path):
    runner = _FakeRunner({"view": _Result(0)})
    sink = make_archive_sink(tmp_path, upload=True, runner=runner)
    sink([_row(1400.0, "CE", 250000)], TRADE_DATE)
    assert (tmp_path / "options_2025-08-18.parquet").exists()
    assert "upload" in _subcommands(runner)
