"""Job health, outside-service limits and Telegram alarms (Arjun 2026-11-22: "yeah...add them" + "there should be
something in the swing trader website.....like an health and efficiency page...that tracks it").

Every scheduled job (EOD scan, news capture) records ONE row in `job_runs` when it ends: when it ran, whether it
WORKED (status + items written, not just "it ran"), the Dhan login result, Dhan calls made, the database size, and the
judged outside limits (`limits_json`). The website's /health page only READS that row, so the rules
live in one place (here) and the page never re-implements them.

Rules: amber ("watch") at 60 % of a limit, red
("broken") at 80 %, measured now or forecast to month end. A limit we cannot measure says so in plain words and is
never shown as fine.

Alarms: a Telegram message only when the overall state CHANGES (to amber, to red, or back to normal), so a standing
problem is not repeated every run. Nothing here may break the job it watches: every DB/network step is wrapped.
"""
from __future__ import annotations

import calendar
import datetime as _dt
import json
import math
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .timeutils import IST, is_trading_day, previous_trading_day

WATCH, BROKEN = 60.0, 80.0
SITE = "https://the-swing-trades.vercel.app"

# Outside limits (checked 2026-11-22). Sources: neon.com/docs/introduction/plans, docs.github.com (Actions billing),
# Dhan support answer 2026-10-15 (data 100k calls/day). NOT a limit: an "18:00 Dhan cutoff" -- scans ran fine to 18:19
# (Aug-Sep 2026) and at 01:38 (13 Oct), so the scan's run time is judged against GitHub's 6-hour job limit instead.
NEON_STORAGE_BYTES = 536_870_912          # Free plan: 0.5 GB per project
NEON_COMPUTE_CU_H = 100.0                 # Free plan: 100 CU-hours per project per month
NEON_IDLE_MIN = 5                         # Free Neon sleeps only after 5 idle minutes
NEON_MIN_CU = 0.25                        # and runs at least 0.25 CU while awake
GH_PRIVATE_MIN = 2000                     # Actions minutes a month on a private repo (public repos: free)
GH_SETUP_MIN = 2                          # checkout + pip install before our code starts (not seen by the timer)
DHAN_DATA_PER_DAY = 100_000
GH_JOB_MAX_MIN = 360                      # GitHub Actions cancels any job after 6 hours
# One Dhan account, one active token: a Swing login cancels the NIFTY bots' token at once. The bots log in at 01:10
# (backup 04:10) and use Dhan 08:30-16:50 on weekdays, so a Swing login must stay out of these windows (IST).
BOT_WINDOWS = [((8, 30), (16, 50), True), ((0, 45), (1, 30), False), ((3, 45), (4, 30), False)]  # (from, to, weekdays only)
TRIAL_DAYS = 14                           # new checks run 2 weeks on trial: shown here, Telegram stays quiet
NEWS_MAX_AGE_H = 36                       # news capture runs daily (twice with the fallback)

STATE_RANK = {"ok": 0, "none": 1, "watch": 2, "broken": 3}


def judge(pct: Optional[float]) -> str:
    if pct is None:
        return "ok"
    return "broken" if pct >= BROKEN else "watch" if pct >= WATCH else "ok"


def _item(key, name, used, limit, unit, *, text, when_hit, forecast=None, state=None, how=""):
    pct = None if used is None or not limit else round(100.0 * used / limit, 1)
    fpct = None if forecast is None or not limit else round(100.0 * forecast / limit, 1)
    if state is None:
        worst = max((p for p in (pct, fpct) if p is not None), default=None)
        state = judge(worst)
    return {"key": key, "name": name, "used": used, "limit": limit, "unit": unit, "pct": pct,
            "forecast": forecast, "forecast_pct": fpct, "state": state, "text": text, "when_hit": when_hit, "how": how}


def _none(key, name, unit, why, when_hit):
    return {"key": key, "name": name, "used": None, "limit": None, "unit": unit, "pct": None, "forecast": None,
            "forecast_pct": None, "state": "none", "text": "not measured: " + why, "when_hit": when_hit, "how": ""}


def month_forecast(used: float, now: _dt.datetime) -> Optional[float]:
    days = calendar.monthrange(now.year, now.month)[1]
    elapsed = (now.day - 1) + (now.hour * 60 + now.minute) / 1440.0
    return used * days / elapsed if elapsed >= 1 else None


def awake_minutes(spans) -> float:
    """[(start, end)] job spans -> minutes Neon was awake: each keeps it up NEON_IDLE_MIN after it ends; overlaps merge."""
    total, cur_s, cur_e = 0.0, None, None
    idle = _dt.timedelta(minutes=NEON_IDLE_MIN)
    for s, e in sorted(spans):
        e = max(e, s) + idle
        if cur_e is not None and s <= cur_e:
            cur_e = max(cur_e, e)
            continue
        if cur_e is not None:
            total += (cur_e - cur_s).total_seconds() / 60
        cur_s, cur_e = s, e
    if cur_e is not None:
        total += (cur_e - cur_s).total_seconds() / 60
    return total


def scan_paused(workflow_path: Optional[Path]) -> bool:
    """The scan workflow itself is the single source of truth: an `if: false` line under the job = paused on purpose."""
    try:
        text = Path(workflow_path).read_text(encoding="utf-8")
    except (OSError, TypeError):
        return False
    return re.search(r"^\s+if:\s*false\s*$", text, flags=re.M) is not None


def _ist(t: Optional[_dt.datetime]) -> Optional[_dt.datetime]:
    if t is None:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)).astimezone(IST)


def judge_limits(*, now: _dt.datetime, month_runs: list, last_scan: Optional[dict], last_scan_date: Optional[_dt.date],
                 last_news: Optional[dict], db_bytes: Optional[int], db_hist: list, dhan_calls_today: int,
                 repo_private: Optional[bool], paused: bool) -> list:
    """Pure: inputs read from the DB -> the list of judged limits/health items (one dict each)."""
    now = _ist(now)
    items = []

    # 1. Jobs WORKED (not just ran). The scan is judged by its newest successful trade date vs the last settled session.
    if paused:
        items.append(_item("scan_fresh", "EOD scan", None, None, "", state="ok",
                           text="paused on purpose (scan workflow has `if: false`); last scanned session %s" % (last_scan_date or "none"),
                           when_hit="no new scan results while paused"))
    else:
        ref = now - _dt.timedelta(hours=3)          # give tonight's 17:00 scan until ~19:00 before it counts as missed
        expected = ref.date() if is_trading_day(ref.date()) and ref.time() >= _dt.time(16, 0) else previous_trading_day(ref.date())
        if last_scan_date is None:
            items.append(_item("scan_fresh", "EOD scan", None, None, "", state="broken", text="no successful scan found",
                               when_hit="the dashboard stops updating"))
        else:
            late = last_scan_date < expected
            items.append(_item("scan_fresh", "EOD scan", None, None, "", state="broken" if late else "ok",
                               text=("last scanned session %s, expected %s" if late else "last scanned session %s (up to date)%s")
                               % (last_scan_date, expected if late else ""),
                               when_hit="the dashboard stops updating"))
        if last_scan and last_scan.get("status") == "failed":
            items.append(_item("scan_failed", "Last scan run", None, None, "", state="broken",
                               text="last scan run FAILED: %s" % (last_scan.get("note") or "see the GitHub run log")[:160],
                               when_hit="today's results are missing"))

    if last_news is None:
        items.append(_item("news_fresh", "News capture", None, None, "", state="watch",
                           text="no news-capture run logged yet (the log starts with the next run)", when_hit="news picks stop"))
    else:
        age_h = (now - _ist(last_news["finished_at"])).total_seconds() / 3600
        ok = last_news.get("status") == "success" and age_h <= NEWS_MAX_AGE_H
        items.append(_item("news_fresh", "News capture", None, None, "", state="ok" if ok else "broken",
                           text="last run %s, %.0f h ago, %s, %d items" % (_ist(last_news["finished_at"]).strftime("%d %b %H:%M"),
                                                                          age_h, last_news.get("status"), last_news.get("items") or 0),
                           when_hit="news picks stop"))

    # 2. Dhan login (one account shared with the NIFTY bots: a failing login risks Dhan's lock after repeated failures).
    if last_scan and last_scan.get("dhan_login") in ("ok", "failed"):
        bad = last_scan["dhan_login"] == "failed"
        items.append(_item("dhan_login", "Dhan login", None, None, "", state="broken" if bad else "ok",
                           text="last scan login %s after %d try(s)" % ("FAILED" if bad else "ok", last_scan.get("dhan_login_tries") or 0),
                           when_hit="no data; repeated failures can lock the Dhan account the NIFTY bots also use"))
    else:
        items.append(_item("dhan_login", "Dhan login", None, None, "", state="ok",
                           text="no scan login logged yet" if not paused else "no login while paused (the scan never logs in)",
                           when_hit="no data; repeated failures can lock the shared Dhan account"))

    # 3. Scan run time vs GitHub's 6-hour job limit, and the login slot vs the NIFTY bots' Dhan hours.
    if last_scan and last_scan.get("finished_at") and last_scan.get("started_at"):
        s, e = _ist(last_scan["started_at"]), _ist(last_scan["finished_at"])
        took = max((e - s).total_seconds() / 60, 0)
        items.append(_item("scan_runtime", "Scan run time", round(took, 1), GH_JOB_MAX_MIN, "min",
                           text="last scan took %.0f min (%s-%s IST); GitHub stops a job at 6 h" % (took, s.strftime("%H:%M"), e.strftime("%H:%M")),
                           when_hit="GitHub cancels the scan; that day's results are lost"))
        if last_scan.get("dhan_login") in ("ok", "failed"):
            clash = [w for w in BOT_WINDOWS if _dt.time(*w[0]) <= s.time() < _dt.time(*w[1]) and (not w[2] or s.weekday() < 5)]
            if clash:
                (h1, m1), (h2, m2) = clash[0][0], clash[0][1]
                txt = "logged in at %s IST, INSIDE the NIFTY bots' Dhan hours %02d:%02d-%02d:%02d" % (s.strftime("%a %H:%M"), h1, m1, h2, m2)
            else:
                txt = "logged in at %s IST, outside the NIFTY bots' Dhan hours" % s.strftime("%a %H:%M")
            items.append(_item("login_slot", "Login slot", None, None, "", state="broken" if clash else "ok", text=txt,
                               when_hit="the live bot's Dhan token is cancelled at once (one active token per account)"))
    if not any(i["key"] == "scan_runtime" for i in items):
        items.append(_none("scan_runtime", "Scan run time", "min", "no scan logged yet", "GitHub cancels the scan after 6 h"))

    # 4. Neon storage (+ when it fills, from the size history).
    if db_bytes is None:
        items.append(_none("neon_storage", "Neon storage", "MB", "size query failed this run", "writes fail; reads still work"))
    else:
        fill = ""
        pts = sorted((_ist(t), b) for t, b in db_hist if b)
        if len(pts) >= 2 and (pts[-1][0] - pts[0][0]).days >= 3:
            per_day = (pts[-1][1] - pts[0][1]) / max((pts[-1][0] - pts[0][0]).total_seconds() / 86400, 1)
            if per_day > 0:
                days = (NEON_STORAGE_BYTES * BROKEN / 100 - db_bytes) / per_day
                fill = "; growing %.1f MB/day, red in ~%d days" % (per_day / 1e6, max(days, 0))
        items.append(_item("neon_storage", "Neon storage", round(db_bytes / 1e6, 1), round(NEON_STORAGE_BYTES / 1e6), "MB",
                           text="%.0f of %.0f MB%s" % (db_bytes / 1e6, NEON_STORAGE_BYTES / 1e6, fill),
                           when_hit="writes fail (scans stop saving); reads still work"))

    # 5. Neon compute hours, estimated (lower bound) from our own job times; website reads are not counted.
    m0 = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    spans = [(_ist(r["started_at"]), _ist(r["finished_at"])) for r in month_runs if r.get("finished_at") and _ist(r["started_at"]) >= m0]
    cu_h = awake_minutes(spans) * NEON_MIN_CU / 60
    fc = month_forecast(cu_h, now)
    items.append(_item("neon_compute", "Neon compute", round(cu_h, 2), NEON_COMPUTE_CU_H, "CU-h", forecast=None if fc is None else round(fc, 2),
                       text="estimate %.1f of %.0f CU-h this month%s" % (cu_h, NEON_COMPUTE_CU_H, "" if fc is None else ", month end ~%.0f" % fc),
                       how="lower bound: %d job runs x (run time + %d idle min) at %.2f CU; website reads not counted; "
                           "Neon's own meter needs its API key" % (len(spans), NEON_IDLE_MIN, NEON_MIN_CU),
                       when_hit="database sleeps until next month: scans and the site fail"))

    # 6. GitHub Actions minutes: free on a public repo; 2,000 a month if it is made private.
    gh_min = sum(math.ceil(max((e - s).total_seconds(), 0) / 60) + GH_SETUP_MIN for s, e in spans)
    gfc = month_forecast(gh_min, now)
    if repo_private:
        items.append(_item("gh_minutes", "GitHub Actions", gh_min, GH_PRIVATE_MIN, "min", forecast=None if gfc is None else round(gfc),
                           text="%d of %d min this month%s" % (gh_min, GH_PRIVATE_MIN, "" if gfc is None else ", month end ~%d" % gfc),
                           when_hit="all jobs stop until next month"))
    else:
        items.append(_item("gh_minutes", "GitHub Actions", gh_min, None, "min", state="ok",
                           text="%d min this month; free because the repo is public%s" % (
                               gh_min, "" if gfc is None else " (if made private: month end ~%d of %d)" % (gfc, GH_PRIVATE_MIN)),
                           when_hit="private repo only: all jobs stop until next month"))

    # 7. Dhan data calls today (this project's share; the NIFTY bots count theirs on their own Health page).
    items.append(_item("dhan_calls", "Dhan data calls", dhan_calls_today, DHAN_DATA_PER_DAY, "calls/day",
                       text="%s of %s today (Swing Trades only)" % (format(dhan_calls_today, ","), format(DHAN_DATA_PER_DAY, ",")),
                       when_hit="Dhan refuses calls for a while (the NIFTY bots share the account)"))

    # 8. What we cannot measure yet, said plainly.
    items.append(_none("neon_transfer", "Neon data read out", "GB", "needs a Neon API key (Arjun)", "database locked until next month"))
    items.append(_none("vercel", "Vercel (site)", "", "needs a Vercel token (Arjun); shared with the NIFTY bot site's account",
                       "site may be paused until resumed by hand"))
    return items


def overall(items: list) -> str:
    return max((i["state"] for i in items if i["state"] in ("watch", "broken")), key=lambda s: STATE_RANK[s], default="ok")


def alarm_text(prev: Optional[str], new: str, items: list) -> Optional[str]:
    """Message only on a CHANGE of overall state; None = stay quiet."""
    if new == (prev or "ok"):
        return None
    if new == "ok":
        return "[The Swing Trades] Health back to normal.\n%s/health" % SITE
    label = {"watch": "AMBER (watch)", "broken": "RED (act)"}[new]
    lines = ["- %s: %s" % (i["name"], i["text"]) for i in sorted(items, key=lambda i: -STATE_RANK[i["state"]])
             if i["state"] in ("watch", "broken")]
    return "[The Swing Trades] Health %s\n%s\n%s/health" % (label, "\n".join(lines[:6]), SITE)


# ── recording (DB side) ────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class JobRun:
    job: str
    started_at: _dt.datetime = field(default_factory=lambda: _dt.datetime.now(_dt.timezone.utc))
    status: str = "running"
    trade_date: Optional[_dt.date] = None
    dhan_login: str = "none"
    dhan_login_tries: int = 0
    dhan_calls: int = 0
    items: int = 0
    note: str = ""


def _workflow_path() -> Optional[Path]:
    ws = os.getenv("GITHUB_WORKSPACE")
    if ws:
        return Path(ws) / ".github" / "workflows" / "scan.yml"
    for p in [Path.cwd(), *Path.cwd().parents]:
        if (p / ".github" / "workflows" / "scan.yml").exists():
            return p / ".github" / "workflows" / "scan.yml"
    return None


def _repo_private() -> Optional[bool]:
    v = (os.getenv("REPO_PRIVATE") or "").strip().lower()
    return True if v == "true" else False if v == "false" else None


def _rows(cur, sql, args=()):
    cur.execute(sql, args)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def finish_and_judge(conn, run: JobRun, *, now: Optional[_dt.datetime] = None, alert: Optional[Callable[[str], bool]] = None) -> dict:
    """Write the run's row with judged limits; send a Telegram alarm on a state change. Returns the judged result."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    with conn.cursor() as cur:
        cur.execute("SELECT pg_database_size(current_database())")
        db_bytes = int(cur.fetchone()[0])
        m0 = _ist(now).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month = _rows(cur, "SELECT job, started_at, finished_at FROM job_runs WHERE started_at >= %s", (m0,))
        month.append({"job": run.job, "started_at": run.started_at, "finished_at": now})
        scans = _rows(cur, "SELECT * FROM job_runs WHERE job = 'eod_scan' AND status <> 'skipped' ORDER BY started_at DESC LIMIT 1")
        news = _rows(cur, "SELECT * FROM job_runs WHERE job = 'news_capture' ORDER BY started_at DESC LIMIT 1")
        hist = _rows(cur, "SELECT finished_at, db_bytes FROM job_runs WHERE finished_at >= %s AND db_bytes IS NOT NULL",
                     (now - _dt.timedelta(days=30),))
        prev = _rows(cur, "SELECT alarm_state FROM job_runs WHERE alarm_state IS NOT NULL ORDER BY finished_at DESC LIMIT 1")
        cur.execute("SELECT max(trade_date) FROM scan_runs WHERE status = 'success'")
        last_scan_date = cur.fetchone()[0]
        day0 = _ist(now).replace(hour=0, minute=0, second=0, microsecond=0)
        cur.execute("SELECT coalesce(sum(dhan_calls), 0) FROM job_runs WHERE started_at >= %s", (day0,))
        calls_today = int(cur.fetchone()[0]) + run.dhan_calls

    this = {"status": run.status, "started_at": run.started_at, "finished_at": now, "items": run.items,
            "dhan_login": run.dhan_login, "dhan_login_tries": run.dhan_login_tries, "note": run.note}
    last_scan = this if run.job == "eod_scan" and run.status != "skipped" else (scans[0] if scans else None)
    last_news = this if run.job == "news_capture" else (news[0] if news else None)
    items = judge_limits(now=now, month_runs=month, last_scan=last_scan, last_scan_date=last_scan_date, last_news=last_news,
                         db_bytes=db_bytes, db_hist=[(r["finished_at"], r["db_bytes"]) for r in hist] + [(now, db_bytes)],
                         dhan_calls_today=calls_today, repo_private=_repo_private(), paused=scan_paused(_workflow_path()))
    with conn.cursor() as cur:
        cur.execute("SELECT min(started_at) FROM job_runs")
        first = cur.fetchone()[0] or run.started_at
    trial_end = (_ist(first) + _dt.timedelta(days=TRIAL_DAYS)).date()
    on_trial = _ist(now).date() < trial_end
    items.append(_item("alarm_trial", "Telegram alarms", None, None, "", state="ok",
                       text=("on trial until %s: shown here, not sent (new checks prove themselves first)" % trial_end) if on_trial
                       else "live since %s: one message when the overall state changes" % trial_end,
                       when_hit="-"))
    state = overall(items)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO job_runs (job, started_at, finished_at, status, trade_date, dhan_login, dhan_login_tries,
                                     dhan_calls, items, db_bytes, note, alarm_state, limits_json)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (run.job, run.started_at, now, run.status, run.trade_date, run.dhan_login, run.dhan_login_tries,
             run.dhan_calls, run.items, db_bytes, run.note[:500], state, json.dumps(items, default=str)))
    conn.commit()
    msg = alarm_text(prev[0]["alarm_state"] if prev else None, state, items)
    if msg and alert and not on_trial:
        alert(msg)
    return {"state": state, "items": items, "alarm": msg, "trial": on_trial}


@contextmanager
def recorded_job(job: str, *, connect: Callable, alert: Optional[Callable[[str], bool]] = None, logger=None):
    """`with recorded_job("eod_scan", connect=...) as run:` -> fill run.* inside; on exit (success OR failure) one
    job_runs row is written on a fresh connection. A recording failure is logged and never hides the job's own error."""
    run = JobRun(job=job)
    t0 = time.monotonic()
    try:
        yield run
        if run.status == "running":
            run.status = "success"
    except BaseException as e:
        run.status = "failed"
        run.note = run.note or ("%s: %s" % (type(e).__name__, e))
        raise
    finally:
        try:
            with connect() as conn:
                res = finish_and_judge(conn, run, alert=alert)
            if logger:
                logger.info("health: %s (%d items) in %.0fs" % (res["state"], len(res["items"]), time.monotonic() - t0))
        except Exception as e:  # never break the job it watches
            if logger:
                logger.warning("health recording failed: %s: %s" % (type(e).__name__, e))
