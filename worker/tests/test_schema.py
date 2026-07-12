import re

from swing_trades.db.auto_init import EXPECTED_TABLES, schema_sql


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower())


def test_schema_defines_all_tables():
    sql = _norm(schema_sql())
    for table in EXPECTED_TABLES:
        assert f"create table if not exists {table}" in sql


def test_every_create_is_guarded_idempotent():
    sql = _norm(schema_sql())
    assert "create table " not in sql.replace("create table if not exists ", "")
    assert "create index " not in sql.replace("create index if not exists ", "")


def test_key_unique_constraints_present():
    sql = _norm(schema_sql())
    assert "isin text unique not null" in sql                  # one row per ISIN (Rule 4)
    assert "unique (instrument_id, trade_date)" in sql         # price_history idempotency (Rule 4)
    assert "unique (instrument_id, strategy_id)" in sql        # tracker keyed (stock x strategy) (Rule 2)
    assert "unique (strategy_id, trade_date)" in sql           # one scan_run per (strategy, date)


def test_entry_close_not_null():
    # Rule 3: the permanent entry reference must always exist.
    assert "entry_close numeric(18,4) not null" in _norm(schema_sql())


def test_news_tables_present():
    sql = _norm(schema_sql())
    assert "create table if not exists news_events" in sql
    assert "create table if not exists news_event_sources" in sql
    assert "source_uid text unique not null" in sql          # per-source idempotency (dedup)


def test_catalyst_enum_enforced():
    sql = _norm(schema_sql())
    # the 10 frozen catalyst values are enforced by a CHECK on both tables
    for tag in (
        "results_positive", "order_win", "acquisition", "buyback", "partnership",
        "new_product", "expansion_capex", "rating_upgrade", "fund_raising", "other_positive",
    ):
        assert tag in sql


def test_news_columns_bolt_on_idempotently():
    # Re-running init_db must be a no-op: every added column is guarded with IF NOT EXISTS.
    sql = _norm(schema_sql())
    for col in ("catalyst_tag", "catalyst_source", "catalyst_decision", "llm_event_type", "llm_sentiment"):
        assert f"add column if not exists {col}" in sql
