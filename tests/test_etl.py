import os
import sqlite3
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl_pipeline import QualityLog, clean, client_summary, run, tie_out  # noqa: E402
from generate_data import generate  # noqa: E402


def raw():
    return {
        "clients": pd.DataFrame({"client_id": [1, 2], "name": ["  ANA ITO ", "Ben Chen"], "age": [40, None],
                                 "wealth_segment": [" high net worth", "Affluent"]}),
        "accounts": pd.DataFrame({"account_id": [10, 11], "client_id": [1, 2],
                                  "account_type": ["roth ira ", "IRA"], "balance": [1000.0, 500.0]}),
        "holdings": pd.DataFrame({"holding_id": [1, 2, 2, 3], "account_id": [10, 10, 10, 11],
                                  "asset_class": ["Equities", "Fixed Income", "Fixed Income", "Equities"],
                                  "market_value": [700.0, 300.0, 300.0, 550.0]}),
        "transactions": pd.DataFrame({"transaction_id": [1, 2, 3], "account_id": [10, 10, 99],
                                      "date": ["2025-01-01", "2025-02-01", "2025-03-01"],
                                      "amount": [100.0, -5.0, 1.0], "type": ["Contribution", "Fee", "Dividend"]}),
    }


def test_cleaning_normalizes_and_logs():
    log = QualityLog()
    d = clean(raw(), log)
    assert d["clients"]["name"].tolist() == ["Ana Ito", "Ben Chen"]
    assert d["clients"]["wealth_segment"].tolist() == ["High Net Worth", "Affluent"]
    assert d["accounts"]["account_type"].tolist() == ["Roth IRA", "IRA"]
    assert len(d["holdings"]) == 3                      # duplicate removed
    assert 99 not in d["transactions"]["account_id"].values  # orphan removed
    checks = set(log.frame()["check"])
    assert "removed exact duplicate rows" in checks
    assert "removed transactions for unknown accounts" in checks


def test_tie_out_flags_only_mismatched_accounts():
    d = clean(raw(), QualityLog())
    breaks = tie_out(d["accounts"], d["holdings"], QualityLog())
    assert breaks["account_id"].tolist() == [11]
    assert breaks["difference"].iloc[0] == 50.0


def test_client_summary_allocation_and_drift():
    s = client_summary(clean(raw(), QualityLog())).set_index("client_id")
    assert s.loc[1, "Equities_pct"] == 70.0
    assert s.loc[1, "target_equity_pct"] == 70.0 and not s.loc[1, "rebalance_flag"]
    assert s.loc[1, "fee_bps"] == 50.0                 # $5 fee on $1,000
    assert not s.loc[2, "rebalance_flag"]              # unknown age is never flagged


def test_end_to_end(tmp_path):
    data = tmp_path / "data"
    generate(15, seed=1, out_dir=str(data))
    summary, quality, breaks = run(str(data), str(tmp_path / "build"))
    assert len(summary) == 15
    assert len(breaks) == 3                            # generator injects three mismatches
    with sqlite3.connect(tmp_path / "build" / "wealth.db") as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"clients", "client_summary", "data_quality_log", "balance_breaks"} <= tables
