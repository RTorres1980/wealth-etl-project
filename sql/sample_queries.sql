-- Run against build/wealth.db:  sqlite3 build/wealth.db < sql/sample_queries.sql

-- AUM and client count by segment
SELECT wealth_segment, COUNT(*) AS clients, ROUND(SUM(total_assets), 0) AS aum
FROM client_summary GROUP BY wealth_segment ORDER BY aum DESC;

-- Clients whose equity allocation has drifted from their age-based target
SELECT name, age, ROUND(Equities_pct, 1) AS equity_pct, target_equity_pct,
       ROUND(equity_drift_pts, 1) AS drift_pts
FROM client_summary WHERE rebalance_flag = 1 ORDER BY ABS(equity_drift_pts) DESC;

-- Net new money by month
SELECT strftime('%Y-%m', date) AS month, ROUND(SUM(amount), 0) AS net_flows
FROM transactions WHERE type IN ('Contribution', 'Withdrawal') GROUP BY month ORDER BY month;

-- Accounts whose holdings do not tie to the reported balance
SELECT account_id, client_id, balance, holdings_total, difference FROM balance_breaks;
