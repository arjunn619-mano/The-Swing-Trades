"""Pull the option Parquet archive from the GitHub Release to a local folder for offline
analysis. Needs the `gh` CLI authenticated (run `gh auth login` once).

    python scripts/sync_option_archive.py [DEST_DIR]

DEST_DIR defaults to ./OptionArchive. Crunch later with: pandas.read_parquet(<file>).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TAG = "option-archive"


def main() -> None:
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("OptionArchive")
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Downloading '{TAG}' assets -> {dest} ...", flush=True)
    result = subprocess.run(
        ["gh", "release", "download", TAG, "-D", str(dest), "--pattern", "*.parquet", "--clobber"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        sys.exit(result.returncode)
    files = sorted(p.name for p in dest.glob("*.parquet"))
    print(f"Done. {len(files)} file(s) in {dest}.", flush=True)


if __name__ == "__main__":
    main()
