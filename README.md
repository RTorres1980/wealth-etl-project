# Wealth ETL Project

## Overview
This project demonstrates the abilities of a **wealth advisor turned data analyst** by building an **ETL (Extract, Transform, Load)** pipeline.  
It simulates financial data from multiple sources (clients, investments, and transactions), cleans and transforms the data, and loads it into a structured format for analysis.

The project highlights skills in:
- Data extraction from CSV and JSON sources
- Data cleaning and transformation with **Pandas**
- Aggregation of client investment performance
- Loading data into a SQLite database for analysis
- Reusable ETL pipeline design

---

## Features
- **Extract**: Pulls client, investment, and transaction data from CSV/JSON.
- **Transform**: Cleans missing values, normalizes text, and aggregates transaction-level returns.
- **Load**: Stores cleaned and structured data into a SQLite database (`wealth_data.db`).
- **Reporting**: Generates summary outputs showing client wealth performance.

---

## Tech Stack
- **Python 3**
- **Pandas** (data manipulation)
- **SQLite3** (database storage)
- **OS & JSON** (file handling)

---

## File Structure
