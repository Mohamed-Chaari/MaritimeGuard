# MaritimeGuard AI

**End-to-end Maritime Intelligence & Supply Chain Risk Platform**
PFA · AIS data lake → dimensional warehouse → OLAP → ML → API → web

---

## Overview

MaritimeGuard AI is a real-time data engineering and AI platform that tracks
global commercial vessel movements, predicts shipping delays and port
congestion, detects suspicious AIS blackouts (illicit activity/smuggling risk),
and exposes natural language querying via a Text-to-SQL GenAI engine with
strict security guardrails.

The project ingests **50,000+ AIS vessel positions** across the Gulf of Mexico,
models them as a **galaxy schema** with slowly changing dimensions, enriches
them with **marine weather** and **port reference data**, and serves everything
through an **API and interactive Deck.gl map**.

---

## Architecture

```
MarineCadastre.gov (AIS)  →  Python loaders  →  DuckDB  →  dbt (bronze/silver/gold)
Digitraffic.fi (live AIS)                                      ↓
Open-Meteo (marine weather)                              Galaxy Schema
NGA World Port Index                                    (3 facts + 4 dims)
                                                              ↓
                                                    scikit-learn / XGBoost
                                                    Isolation Forest
                                                              ↓
                                                         FastAPI
                                                     (REST + WebSocket)
                                                              ↓
                                                      Deck.gl dark map
                                                      "Ask Your Data"
```

### Data model — galaxy schema

| Table | Grain | Description |
|-------|-------|-------------|
| `fct_vessel_positions` | (vessel, timestamp) | AIS position snapshots with Haversine distance |
| `fct_port_calls` | port call event | Arrival/departure with duration and delay metrics |
| `fct_ais_anomalies` | anomaly event | Blackouts, speed jumps, risk scores |
| `dim_vessels` | vessel (SCD2) | MMSI, IMO, type, dimensions, flag |
| `dim_ports` | port | NGA WPI: coordinates, depth, facilities |
| `dim_time` | hour | 2-year hourly grain with maritime watches |
| `dim_weather_zones` | zone | Maritime chokepoints and shipping regions |
| `obt_vessel_tracking` | denormalized | Wide table for fast BI |

### ML models

| Model | Type | Target |
|-------|------|--------|
| Vessel Arrival Delay | XGBoost Classifier | Port stay > 48h |
| Voyage Duration | XGBoost Regressor | Stay duration in hours |
| AIS Blackout Detector | Isolation Forest | Anomalous signal gaps |

---

## Data sources

| Source | Type | License |
|--------|------|---------|
| [MarineCadastre.gov](https://marinecadastre.gov/ais/) | Historical AIS (GeoParquet) | Public domain (US Gov) |
| [Digitraffic.fi](https://www.digitraffic.fi/en/marine-traffic/) | Real-time AIS (REST/MQTT) | CC BY 4.0 |
| [Open-Meteo Marine API](https://open-meteo.com/en/docs/marine-weather-api) | Wave, wind, currents | CC BY 4.0 |
| [NGA World Port Index](https://msi.nga.mil/) | Port reference (~3,700 ports) | Public domain (US Gov) |

---

## Quick start

```bash
pip install -r requirements.txt

python scripts/build_demo.py          # build warehouse, print KPIs
python ml/run_experiments.py          # train 3 ML models
python tests/test_ask_data_safety.py  # 17/17 safety checks

# Start the API and open the demo map
uvicorn main:app --reload --app-dir serving/api
# http://localhost:8000/demo   (Deck.gl vessel map)
# http://localhost:8000/docs   (Swagger API docs)
```

---

## Repository layout

```
maritimeguard/
├── data/wpi/                   NGA World Port Index
├── ingestion/
│   ├── ais/                    MarineCadastre bulk + Digitraffic live
│   ├── weather/                Open-Meteo marine weather
│   └── ports/                  NGA WPI loader
├── warehouse/dbt/              bronze → silver → gold, snapshots, tests
├── ml/                         3 ML models (delay, voyage, anomaly)
├── serving/api/                FastAPI + WebSocket + Text-to-SQL + AI briefing
├── tests/                      Safety test suite (17/17)
├── scripts/build_demo.py       Reproducible end-to-end build
└── docs/                       Architecture, profiling, source study
```

---

## API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /kpis` | Maritime KPIs |
| `GET /vessels/active` | Recently active vessels |
| `GET /vessels/{mmsi}` | Vessel profile + latest position |
| `GET /vessels/delays` | ML-predicted delayed vessels |
| `GET /ports/top` | Top ports by traffic |
| `GET /ports/{id}/congestion` | Port congestion metrics |
| `GET /anomalies/recent` | Recent AIS anomalies |
| `WS /ws/live-vessels` | Live vessel position stream |
| `POST /ask` | Text-to-SQL (17/17 security guardrails) |
| `POST /ai-briefing` | AI supply chain risk summary |
| `GET /demo` | Deck.gl dark-mode vessel map |
