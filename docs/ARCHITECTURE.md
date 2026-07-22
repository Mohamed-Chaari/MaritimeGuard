# Architecture & Design Decisions

This document outlines the architectural decisions for **MaritimeGuard AI**.

## 1. Engine: DuckDB
We chose **DuckDB** over a traditional cloud data warehouse (Snowflake/BigQuery) because:
1. **Embedded & Local First:** No network latency, processes 1M+ rows per second on a laptop.
2. **Columnar:** Excellent for OLAP analytical queries (e.g., aggregation by vessel type or port).
3. **Free & Portable:** A single `.duckdb` file can be distributed easily.

## 2. dbt Data Modeling (Galaxy Schema)
We organize data into Bronze (raw), Silver (cleansed), and Gold (marts).
The Gold layer uses a **Galaxy Schema** because maritime data involves multiple concurrent event grains:
- `fct_vessel_positions`: Granularity = 1 AIS ping.
- `fct_port_calls`: Granularity = 1 port visit (arrival to departure).
- `fct_ais_anomalies`: Granularity = 1 suspicious event.

These share **Conformed Dimensions**:
- `dim_vessels` (SCD Type 2 to handle vessel name/flag changes)
- `dim_ports`
- `dim_time`
- `dim_weather_zones`

## 3. Serving Layer & Security
We expose the data via FastAPI. The primary risk is the "Ask Your Data" natural language endpoint.
We use a **4-layer defense** strategy:
1. **Read-only Connection:** `duckdb.connect(DB_PATH, read_only=True)`.
2. **Table Allowlist:** Queries can only target tables explicitly in the `gold` schema.
3. **Keyword Blocklist:** Rejects DDL (CREATE, DROP) and DML (INSERT, DELETE).
4. **Function Blocklist:** Rejects filesystem/network functions (`read_csv`, `read_json`, `httpfs`).
