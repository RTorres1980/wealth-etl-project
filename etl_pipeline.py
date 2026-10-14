"""etl_pipeline.py
Extract client, account and holding data (CSV) plus a custodian transaction feed (JSON),
clean and validate it, build client-level wealth analytics, and load everything into SQLite.

Outputs in build/:
  wealth.db               SQLite database (raw-cleaned tables + client_summary + data_quality_log)
  wealth_report.csv       one row per client
  data_quality_log.csv    every cleaning action and validation exception
  allocation_chart.png    asset allocation by client segment

Usage: python etl_pipeline.py [--data data] [--build build]
"""
import argparse
import json
import os
import sqlite3

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

TOLERANCE = 1.00          # $ difference allowed between account balance and sum of holdings
DRIFT_THRESHOLD = 10.0    # percentage points of equity drift that triggers a rebalance flag
SEGMENTS = {"mass affluent": "Mass Affluent", "affluent": "Affluent", "high net worth": "High Net Worth"}


# ---------------------------------------------------------------- extract
def extract(data_dir):
    with open(os.path.join(data_dir, "transactions.json")) as f:
        feed = json.load(f)
    return {
        "clients": pd.read_csv(os.path.join(data_dir, "clients.csv")),
        "accounts": pd.read_csv(os.path.join(data_dir, "accounts.csv")),
        "holdings": pd.read_csv(os.path.join(data_dir, "holdings.csv")),
        "transactions": pd.json_normalize(feed["transactions"]),
    }


# ---------------------------------------------------------------- transform
class QualityLog:
    def __init__(self):
        self.rows = []

    def add(self, table, check, count, detail=""):
        if count:
            self.rows.append({"table": table, "check": check, "rows_affected": int(count), "detail": detail})

    def frame(self):
        return pd.DataFrame(self.rows, columns=["table", "check", "rows_affected", "detail"])


def clean(raw, log):
    c = raw["clients"].copy()
    name_fix = c["name"] != c["name"].str.strip().str.title()
    c["name"] = c["name"].str.strip().str.title()
    log.add("clients", "normalized name casing/whitespace", name_fix.sum())
    seg_raw = c["wealth_segment"]
    c["wealth_segment"] = seg_raw.str.strip().str.lower().map(SEGMENTS)
    log.add("clients", "normalized wealth_segment label", (seg_raw != c["wealth_segment"]).sum())
    log.add("clients", "missing age (kept, excluded from glide-path check)", c["age"].isna().sum())

    a = raw["accounts"].copy()
    fixed_types = a["account_type"].str.strip().str.lower().map(
        {"ira": "IRA", "roth ira": "Roth IRA", "401k": "401k", "brokerage": "Brokerage", "trust": "Trust"})
    log.add("accounts", "normalized account_type", (fixed_types != a["account_type"]).sum())
    a["account_type"] = fixed_types

    h = raw["holdings"]
    dupes = h.duplicated()
    log.add("holdings", "removed exact duplicate rows", dupes.sum())
    h = h[~dupes].copy()

    t = raw["transactions"].copy()
    t["date"] = pd.to_datetime(t["date"])
    orphan = ~t["account_id"].isin(a["account_id"])
    log.add("transactions", "removed transactions for unknown accounts", orphan.sum())
    t = t[~orphan]
    return {"clients": c, "accounts": a, "holdings": h, "transactions": t}


def tie_out(accounts, holdings, log):
    """Account balance must equal the sum of its holdings (within tolerance)."""
    hv = holdings.groupby("account_id")["market_value"].sum().round(2).rename("holdings_total")
    tie = accounts.set_index("account_id")[["client_id", "balance"]].join(hv)
    tie["difference"] = (tie["holdings_total"] - tie["balance"]).round(2)
    breaks = tie[tie["difference"].abs() > TOLERANCE].reset_index()
    log.add("accounts", f"balance does not tie to holdings (> ${TOLERANCE:.2f})", len(breaks),
            "; ".join(f"acct {r.account_id}: diff ${r.difference:,.2f}" for r in breaks.itertuples()))
    return breaks


def client_summary(d):
    c, a, h, t = d["clients"], d["accounts"], d["holdings"], d["transactions"]
    h = h.merge(a[["account_id", "client_id"]], on="account_id")
    alloc = h.pivot_table(index="client_id", columns="asset_class", values="market_value",
                          aggfunc="sum", fill_value=0)
    alloc_pct = alloc.div(alloc.sum(axis=1), axis=0).mul(100).add_suffix("_pct")

    t = t.merge(a[["account_id", "client_id"]], on="account_id")
    flows = (t.pivot_table(index="client_id", columns="type", values="amount", aggfunc="sum", fill_value=0)
             .reindex(columns=["Contribution", "Withdrawal", "Dividend", "Fee"], fill_value=0))

    s = (c.set_index("client_id")
         .join(a.groupby("client_id").agg(accounts=("account_id", "count"), total_assets=("balance", "sum")))
         .join(alloc_pct)
         .join(flows)
         .fillna({"Contribution": 0, "Withdrawal": 0, "Dividend": 0, "Fee": 0}))
    s["net_flows"] = s[["Contribution", "Withdrawal"]].sum(axis=1)
    s["fee_bps"] = s["Fee"].abs() / s["total_assets"] * 10_000
    s["target_equity_pct"] = (110 - s["age"]).clip(20, 90)
    s["equity_drift_pts"] = s["Equities_pct"] - s["target_equity_pct"]
    s["rebalance_flag"] = s["equity_drift_pts"].abs() > DRIFT_THRESHOLD
    return s.reset_index().round(2)


# ---------------------------------------------------------------- load
def load(tables, db_path):
    with sqlite3.connect(db_path) as conn:
        for name, df in tables.items():
            df.to_sql(name, conn, if_exists="replace", index=False)


def allocation_chart(summary, path):
    cols = [c for c in summary.columns if c.endswith("_pct") and c != "target_equity_pct"]
    by_seg = summary.groupby("wealth_segment")[cols].mean()
    by_seg.columns = [c.replace("_pct", "") for c in cols]
    ax = by_seg.plot.barh(stacked=True, figsize=(8, 3.5), width=0.7)
    ax.set_xlabel("Average allocation (%)")
    ax.set_ylabel("")
    ax.set_title("Asset allocation by client segment")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.45), ncol=4, frameon=False)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def run(data_dir="data", build_dir="build"):
    os.makedirs(build_dir, exist_ok=True)
    log = QualityLog()
    data = clean(extract(data_dir), log)
    breaks = tie_out(data["accounts"], data["holdings"], log)
    summary = client_summary(data)
    quality = log.frame()

    load({**data, "client_summary": summary, "balance_breaks": breaks, "data_quality_log": quality},
         os.path.join(build_dir, "wealth.db"))
    summary.to_csv(os.path.join(build_dir, "wealth_report.csv"), index=False)
    quality.to_csv(os.path.join(build_dir, "data_quality_log.csv"), index=False)
    allocation_chart(summary, os.path.join(build_dir, "allocation_chart.png"))

    print(f"Clients: {len(summary)} | AUM: ${summary['total_assets'].sum():,.0f} | "
          f"Rebalance flags: {int(summary['rebalance_flag'].sum())} | Balance breaks: {len(breaks)}")
    print("\nData-quality log:")
    print(quality.drop(columns="detail").to_string(index=False))
    return summary, quality, breaks


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", default="data")
    p.add_argument("--build", default="build")
    args = p.parse_args()
    run(args.data, args.build)
