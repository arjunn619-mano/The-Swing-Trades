from swing_trades.utils.logging_setup import setup_logging


def test_rotation_purges_old_logs(tmp_path):
    logger = setup_logging(
        tmp_path, name="test_rot", max_bytes=1000, backup_count=3, also_console=False
    )
    for i in range(5000):
        logger.info("x" * 50 + f" {i}")
    for h in logger.handlers:
        h.flush()
    files = list(tmp_path.glob("scan.log*"))
    # scan.log + at most backup_count rotated files
    assert len(files) <= 4
    assert (tmp_path / "scan.log").exists()


def test_setup_is_idempotent(tmp_path):
    l1 = setup_logging(tmp_path, name="test_idem", also_console=False)
    n1 = len(l1.handlers)
    l2 = setup_logging(tmp_path, name="test_idem", also_console=False)
    assert len(l2.handlers) == n1  # handlers don't accumulate on repeat calls


def test_log_line_is_json(tmp_path):
    import json

    logger = setup_logging(tmp_path, name="test_json", also_console=False)
    logger.info("hello world")
    for h in logger.handlers:
        h.flush()
    line = (tmp_path / "scan.log").read_text(encoding="utf-8").splitlines()[0]
    payload = json.loads(line)
    assert payload["msg"] == "hello world"
    assert payload["level"] == "INFO"
