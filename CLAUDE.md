# CLAUDE.md — MaritimeGuard AI

Context for Claude Code. This is a **PFA (8 credits)**, so rigour and written
justification matter as much as working code.

## What this is

End-to-end Maritime Intelligence & Supply Chain Risk Platform. Tracks vessel
movements via AIS, predicts delays, detects AIS blackouts (anomaly detection),
and serves everything through a guarded API with a dark-mode Deck.gl map.

## Locked decisions — do not re-litigate

- **Engine: DuckDB.** Free, embedded, columnar. Not SQL Server, not Snowflake.
  dbt profile is `dbt-duckdb`; warehouse file `warehouse/maritimeguard.duckdb`.
- **Galaxy schema.** Three facts sharing conformed dimensions:
  `fct_vessel_positions` (position grain), `fct_port_calls` (event grain),
  `fct_ais_anomalies` (anomaly grain).
- **SCD Type 2** on vessels via `snapshots/dim_vessels_scd2.sql`.
- **OBT** wide serving table `gold/obt_vessel_tracking.sql`.
- **Layers:** bronze (raw 1:1) → silver (clean, dedup, validate) → gold.

## Data sources

1. **MarineCadastre.gov** — Historical AIS positions (GeoParquet, public domain)
2. **Digitraffic.fi** — Real-time AIS (REST API, CC BY 4.0)
3. **Open-Meteo Marine API** — Wave height, wind speed, ocean currents (free)
4. **NGA World Port Index** — ~3,700 ports (public domain)

## ML models

1. **Vessel Arrival Delay Classifier** — XGBoost, predicts extended port stays
2. **Voyage Duration Regressor** — XGBoost, predicts stay duration
3. **AIS Blackout Anomaly Detector** — Isolation Forest, flags suspicious gaps

## GenAI + Security

- `serving/api/ask_data.py` — 4 defense layers: statement shape, keyword
  blocklist, table allowlist from live schema, read-only DuckDB connection.
  17/17 safety tests pass including SQL injection, path traversal, and
  file-access function blocking.
- `serving/api/briefing.py` — LLM executive supply chain risk summaries.
- Requires `ANTHROPIC_API_KEY` in `.env`.

## Repo map

- `warehouse/dbt/` — models, snapshots, tests, macros
- `scripts/build_demo.py` — builds warehouse from sample/real data
- `ml/run_experiments.py` — three ML models
- `ingestion/ais/` — MarineCadastre loader + Digitraffic poller
- `ingestion/weather/` — Open-Meteo marine weather
- `ingestion/ports/` — NGA World Port Index loader
- `serving/api/` — FastAPI (11 endpoints + WebSocket + demo map)
- `tests/` — SQL safety test suite

## How to run

```bash
pip install -r requirements.txt
python scripts/build_demo.py          # build warehouse
python ml/run_experiments.py          # train ML models
python tests/test_ask_data_safety.py  # safety suite
uvicorn main:app --reload --app-dir serving/api
```

## Conventions

- SQL: DuckDB dialect. Models are pure `select`. One grain per fact.
- Dimensions deduplicated on the business key (GROUP BY), never SELECT DISTINCT.
- Report metrics honestly — if a model does not beat its baseline, say so.
- Every new layer must trace to a course concept.
