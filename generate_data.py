"""generate_data.py
Creates a synthetic wealth-management dataset across two source formats (CSV and JSON),
with the kinds of defects real advisor-platform extracts contain: inconsistent casing and
whitespace, missing values, duplicate rows, and holdings that don't tie to account balances.

Usage: python generate_data.py [--clients 40] [--seed 3]
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

FIRST = ["Ana", "Ben", "Carla", "David", "Elena", "Frank", "Grace", "Hector", "Iris", "Jamal",
         "Kira", "Luis", "Maya", "Noah", "Olivia", "Pedro", "Quinn", "Rosa", "Sam", "Tara"]
LAST = ["Alvarez", "Brooks", "Chen", "Diaz", "Evans", "Foster", "Garcia", "Hughes", "Ito", "Jensen"]
ACCOUNT_TYPES = ["IRA", "Roth IRA", "401k", "Brokerage", "Trust"]
ASSET_CLASSES = ["Equities", "Fixed Income", "Cash", "Alternatives"]


def segment(total):
    if total >= 1_000_000:
        return "High Net Worth"
    if total >= 250_000:
        return "Affluent"
    return "Mass Affluent"


def generate(n_clients=40, seed=3, out_dir="data"):
    rng = np.random.default_rng(seed)
    os.makedirs(out_dir, exist_ok=True)
    clients, accounts, holdings, txns = [], [], [], []
    acct_id, hold_id, txn_id = 100, 1000, 5000

    for cid in range(1, n_clients + 1):
        age = int(rng.integers(28, 78))
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        client_total = 0
        for _ in range(int(rng.integers(1, 4))):
            acct_id += 1
            balance = round(float(rng.lognormal(12, 1.0)), 2)
            client_total += balance
            # Allocation drifts around an age-based glide path (equity ~ 110 - age)
            eq = np.clip((110 - age) / 100 + rng.normal(0, 0.12), 0.1, 0.95)
            rest = rng.dirichlet([5, 1, 1.5]) * (1 - eq)
            weights = dict(zip(ASSET_CLASSES, [eq, *rest]))
            for ac, w in weights.items():
                hold_id += 1
                holdings.append({"holding_id": hold_id, "account_id": acct_id, "asset_class": ac,
                                 "market_value": round(balance * w, 2)})
            accounts.append({"account_id": acct_id, "client_id": cid,
                             "account_type": rng.choice(ACCOUNT_TYPES), "balance": balance})
            for _ in range(int(rng.integers(2, 10))):
                txn_id += 1
                kind = rng.choice(["Contribution", "Withdrawal", "Dividend", "Fee"], p=[0.4, 0.2, 0.3, 0.1])
                amt = {"Contribution": rng.uniform(500, 25000), "Withdrawal": -rng.uniform(500, 20000),
                       "Dividend": rng.uniform(50, 3000), "Fee": -rng.uniform(25, 1500)}[kind]
                date = pd.Timestamp("2025-01-01") + pd.Timedelta(days=int(rng.integers(0, 270)))
                txns.append({"transaction_id": txn_id, "account_id": acct_id, "date": str(date.date()),
                             "amount": round(float(amt), 2), "type": kind})
        clients.append({"client_id": cid, "name": name, "age": age, "wealth_segment": segment(client_total)})

    clients_df, accounts_df, holdings_df = map(pd.DataFrame, (clients, accounts, holdings))

    # --- inject realistic defects ---
    messy = rng.choice(len(clients_df), 6, replace=False)
    clients_df.loc[messy[:3], "name"] = clients_df.loc[messy[:3], "name"].str.upper() + "  "
    clients_df.loc[messy[3:5], "age"] = np.nan
    clients_df.loc[messy[5], "wealth_segment"] = " high net worth"
    accounts_df.loc[rng.choice(len(accounts_df), 2, replace=False), "account_type"] = "roth ira "
    holdings_df = pd.concat([holdings_df, holdings_df.sample(3, random_state=seed)], ignore_index=True)
    off = rng.choice(len(holdings_df), 3, replace=False)
    holdings_df.loc[off, "market_value"] = (holdings_df.loc[off, "market_value"] * 1.15).round(2)

    clients_df.to_csv(os.path.join(out_dir, "clients.csv"), index=False)
    accounts_df.to_csv(os.path.join(out_dir, "accounts.csv"), index=False)
    holdings_df.to_csv(os.path.join(out_dir, "holdings.csv"), index=False)
    with open(os.path.join(out_dir, "transactions.json"), "w") as f:
        json.dump({"source": "custodian_feed", "transactions": txns}, f, indent=1)
    print(f"Wrote {n_clients} clients, {len(accounts_df)} accounts, {len(holdings_df)} holdings, "
          f"{len(txns)} transactions to {out_dir}/")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--clients", type=int, default=40)
    p.add_argument("--seed", type=int, default=3)
    a = p.parse_args()
    generate(a.clients, a.seed)
