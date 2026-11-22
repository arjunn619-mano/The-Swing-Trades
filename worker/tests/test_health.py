"""Health log + limits judge + alarms (swing_trades/utils/health.py)."""
import datetime as dt
import os
from pathlib import Path

import pytest

from swing_trades.utils import health as H
from swing_trades.utils.timeutils import IST

REPO = Path(__file__).resolve().parents[2]


def t(day, hh, mm=0):
    return dt.datetime(2026, 11, day, hh, mm, tzinfo=IST)


def base(**kw):
    args = dict(now=t(24, 19), month_runs=[], last_scan=None, last_scan_date=dt.date(2026, 11, 24),
                last_news={"status": "success", "finished_at": t(24, 16, 33), "items": 40}, db_bytes=100_000_000,
                db_hist=[], dhan_calls_today=0, repo_private=False, paused=False)
    args.update(kw)
    return {i["key"]: i for i in H.judge_limits(**args)}


def test_thresholds_are_60_and_80():
    assert H.judge(59.9) == "ok" and H.judge(60) == "watch" and H.judge(80) == "broken" and H.judge(None) == "ok"


def test_scan_runtime_vs_github_six_hours():
    scan = {"status": "success", "started_at": t(24, 17, 0), "finished_at": t(24, 17, 52), "dhan_login": "ok", "dhan_login_tries": 1}
    assert base(last_scan=scan)["scan_runtime"]["state"] == "ok"            # the 52-min October scans are fine
    scan["finished_at"] = t(24, 21, 0)                                       # 240 of 360 min = 67 %
    assert base(last_scan=scan)["scan_runtime"]["state"] == "watch"
    scan["finished_at"] = t(24, 22, 0)
    assert base(last_scan=scan)["scan_runtime"]["state"] == "broken"


def test_login_inside_the_bots_hours_is_red():
    ok = {"status": "success", "started_at": t(24, 17, 0), "finished_at": t(24, 17, 50), "dhan_login": "ok"}
    assert base(last_scan=ok)["login_slot"]["state"] == "ok"
    rescan = dict(ok, started_at=t(24, 16, 20), finished_at=t(24, 16, 40))  # a manual re-scan at 16:20 on a Tuesday
    assert base(last_scan=rescan)["login_slot"]["state"] == "broken"
    night = dict(ok, started_at=t(24, 1, 0), finished_at=t(24, 1, 20))      # next to the bots' 01:10 login
    assert base(last_scan=night)["login_slot"]["state"] == "broken"
    weekend = dict(ok, started_at=t(22, 11, 0), finished_at=t(22, 11, 20))  # Sunday daytime: bots not trading
    assert base(last_scan=weekend)["login_slot"]["state"] == "ok"
    no_login = dict(ok, dhan_login="none")
    assert "login_slot" not in base(last_scan=no_login)


def test_missed_scan_is_red_but_paused_is_ok():
    stale = dt.date(2026, 11, 20)
    assert base(last_scan_date=stale)["scan_fresh"]["state"] == "broken"
    assert base(last_scan_date=stale, paused=True)["scan_fresh"]["state"] == "ok"
    assert "paused on purpose" in base(last_scan_date=stale, paused=True)["scan_fresh"]["text"]


def test_tonights_scan_gets_time_before_counting_as_missed():
    # 17:30 on a trading day: yesterday's scan is still the expected one
    assert base(now=t(24, 17, 30), last_scan_date=dt.date(2026, 11, 23))["scan_fresh"]["state"] == "ok"


def test_failed_login_is_red():
    scan = {"status": "failed", "started_at": t(24, 17), "finished_at": t(24, 17, 1), "dhan_login": "failed",
            "dhan_login_tries": 2, "note": "RuntimeError: Dhan login failed"}
    r = base(last_scan=scan)
    assert r["dhan_login"]["state"] == "broken" and r["scan_failed"]["state"] == "broken"


def test_stale_news_is_red():
    assert base(last_news={"status": "success", "finished_at": t(22, 16), "items": 3})["news_fresh"]["state"] == "broken"


def test_storage_and_fill_forecast():
    r = base(db_bytes=350_000_000, db_hist=[(t(1, 17), 250_000_000), (t(20, 17), 345_000_000)])
    assert r["neon_storage"]["state"] == "watch"                             # 350 of 537 MB = 65 %
    assert "red in ~" in r["neon_storage"]["text"]
    assert base(db_bytes=450_000_000)["neon_storage"]["state"] == "broken"


def test_compute_estimate_merges_idle_and_forecasts():
    runs = [{"started_at": t(d, 17), "finished_at": t(d, 17, 50)} for d in range(1, 24)]
    r = base(month_runs=runs)["neon_compute"]
    assert r["used"] == pytest.approx(23 * 55 * 0.25 / 60, abs=0.01)
    assert r["forecast"] > r["used"] and r["state"] == "ok"


def test_github_minutes_free_when_public_counted_when_private():
    runs = [{"started_at": t(d, 17), "finished_at": t(d, 17, 50)} for d in range(1, 24)]
    pub = base(month_runs=runs)["gh_minutes"]
    assert pub["state"] == "ok" and "free because the repo is public" in pub["text"] and "if made private" in pub["text"]
    priv = base(month_runs=runs, repo_private=True)["gh_minutes"]
    assert priv["used"] == 23 * 52 and priv["state"] == "watch"             # month end ~1,560 of 2,000 = 78 %


def test_unmeasured_limits_say_so():
    r = base()
    assert r["neon_transfer"]["state"] == "none" and r["neon_transfer"]["text"].startswith("not measured")
    assert r["vercel"]["state"] == "none"


def test_awake_minutes_merges_overlaps():
    a, b = t(1, 17), t(1, 17, 3)
    assert H.awake_minutes([(a, a), (b, b)]) == pytest.approx(8)          # 17:00-17:08, one wake
    assert H.awake_minutes([(a, a), (t(1, 18), t(1, 18))]) == pytest.approx(10)


def test_alarm_only_on_state_change():
    items = [{"name": "Login slot", "text": "x", "state": "broken"}]
    assert H.alarm_text("broken", "broken", items) is None
    assert "RED" in H.alarm_text("ok", "broken", items) and "/health" in H.alarm_text("ok", "broken", items)
    assert "back to normal" in H.alarm_text("broken", "ok", [])
    assert H.alarm_text(None, "ok", []) is None


def test_scan_paused_reads_the_real_workflow(tmp_path):
    wf = tmp_path / "scan.yml"
    wf.write_text("jobs:\n  scan:\n    # delete the `if: false` line\n    runs-on: ubuntu-latest\n")
    assert H.scan_paused(wf) is False
    wf.write_text("jobs:\n  scan:\n    if: false\n    runs-on: ubuntu-latest\n")
    assert H.scan_paused(wf) is True
    assert H.scan_paused(None) is False
    real = REPO / ".github" / "workflows" / "scan.yml"
    assert H.scan_paused(real) == ("\n    if: false\n" in real.read_text(encoding="utf-8").replace("\r\n", "\n"))


def test_recording_never_hides_the_jobs_error_and_never_breaks_it():
    def boom():
        raise RuntimeError("db down")
    with pytest.raises(ValueError):
        with H.recorded_job("eod_scan", connect=boom):
            raise ValueError("the job's own error")
    with H.recorded_job("news_capture", connect=boom) as run:   # recording fails silently, job succeeds
        run.items = 1


RUN_DB = bool(os.getenv("RUN_DB_TESTS")) and bool(os.getenv("DATABASE_URL"))


@pytest.mark.skipif(not RUN_DB, reason="set RUN_DB_TESTS=1 and DATABASE_URL to run")
def test_job_row_written_and_alarm_sent_once():
    import psycopg

    from swing_trades.db.auto_init import apply_schema

    url = os.environ["DATABASE_URL"]
    with psycopg.connect(url) as conn:
        apply_schema(conn)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM job_runs")
        conn.commit()
    sent = []
    for _ in range(2):
        with H.recorded_job("news_capture", connect=lambda: psycopg.connect(url), alert=lambda m: sent.append(m) or True) as run:
            run.items = 5
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute("SELECT job, status, items, alarm_state, jsonb_array_length(limits_json), db_bytes > 0 FROM job_runs ORDER BY id")
        rows = cur.fetchall()
    assert len(rows) == 2 and rows[0][:3] == ("news_capture", "success", 5)
    assert rows[0][4] >= 8 and rows[0][5] is True
    assert rows[0][3] == rows[1][3]
    assert sent == []                                             # first 2 weeks: on trial, Telegram stays quiet
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute("SELECT limits_json FROM job_runs ORDER BY id DESC LIMIT 1")
        trial = [i for i in cur.fetchone()[0] if i["key"] == "alarm_trial"][0]
    assert trial["text"].startswith("on trial until")
