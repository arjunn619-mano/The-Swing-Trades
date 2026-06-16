"""Parquet archive for the full daily option snapshot (Planning Pack 11, Phase O4).

The option scan hands every strike (all metrics) to a sink; we write one Parquet file per
trading day and (optionally) upload it as an asset on a rolling GitHub Release, from which the
laptop pulls copies for offline analysis (scripts/sync_option_archive.py). Files, not the DB:
120k+ rows/day compresses to a few MB and is built for pandas crunching."""
from __future__ import annotations

import datetime as _dt
import subprocess
from pathlib import Path
from typing import Callable, Optional, Sequence

import pandas as pd

ARCHIVE_TAG = "option-archive"

# Stable column order so every daily file is schema-compatible for offline concatenation.
ARCHIVE_COLUMNS = [
    "trade_date", "security_id", "underlying_symbol", "instrument_type", "exchange",
    "expiry_date", "strike", "option_type", "lot_size", "ltp", "volume", "oi",
    "previous_oi", "oi_change_pct", "iv", "delta", "theta", "gamma", "vega",
    "underlying_last", "days_to_expiry",
]


def snapshot_filename(trade_date: _dt.date) -> str:
    return f"options_{trade_date.isoformat()}.parquet"


def write_snapshot_parquet(rows: Sequence[dict], trade_date: _dt.date, out_dir) -> Path:
    """Write the full per-strike snapshot to out_dir/options_YYYY-MM-DD.parquet; return the path.
    Always writes (even an empty frame) so a missing file unambiguously means 'scan didn't run'."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(list(rows), columns=ARCHIVE_COLUMNS)
    path = out / snapshot_filename(trade_date)
    df.to_parquet(path, engine="pyarrow", index=False, compression="snappy")
    return path


def _default_runner(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def upload_to_release(
    path,
    tag: str = ARCHIVE_TAG,
    repo: Optional[str] = None,
    title: Optional[str] = None,
    runner: Optional[Callable] = None,
) -> None:
    """Upload one Parquet file as an asset on the rolling `option-archive` release, creating the
    release on first use. Uses the `gh` CLI (GitHub Actions' GITHUB_TOKEN can manage same-repo
    releases). `runner(cmd) -> CompletedProcess`-like is injectable for tests."""
    runner = runner or _default_runner
    path = Path(path)
    repo_args = ["--repo", repo] if repo else []

    # Ensure the release exists (idempotent: create only if `view` fails).
    view = runner(["gh", "release", "view", tag, *repo_args])
    if getattr(view, "returncode", 1) != 0:
        runner([
            "gh", "release", "create", tag,
            "--title", title or "Option archive",
            "--notes", "Daily full option snapshots (Parquet). Planning Pack 11.",
            *repo_args,
        ])
    # Upload (clobber so re-running a day replaces that day's asset).
    up = runner(["gh", "release", "upload", tag, str(path), "--clobber", *repo_args])
    if getattr(up, "returncode", 0) != 0:
        raise RuntimeError(f"gh release upload failed: {getattr(up, 'stderr', '')}")


def make_archive_sink(
    out_dir,
    *,
    upload: bool = False,
    tag: str = ARCHIVE_TAG,
    repo: Optional[str] = None,
    runner: Optional[Callable] = None,
    logger=None,
):
    """Build a snapshot_sink(rows, trade_date) for run_option_scan: write Parquet, optionally upload."""

    def sink(rows, trade_date) -> None:
        path = write_snapshot_parquet(rows, trade_date, out_dir)
        if logger:
            logger.info(f"archive: wrote {len(rows)} rows -> {path}")
        if upload:
            upload_to_release(path, tag=tag, repo=repo, runner=runner)
            if logger:
                logger.info(f"archive: uploaded {path.name} to release '{tag}'")

    return sink
