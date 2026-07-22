# STATUS — MaritimeGuard AI

An honest inventory. Read this before opening the project in an IDE.

Last updated: 2026-07-22

---

## Architecture complete (code written, awaiting first execution)

| Component | Status |
|-----------|--------|
| **Ingestion scripts** | Written: MarineCadastre AIS loader, Digitraffic poller, Open-Meteo weather, NGA WPI |
| **dbt models** | Written: 4 silver staging + 8 gold models + 1 SCD2 snapshot + schema tests |
| **Galaxy schema** | 3 fact tables + 4 dimensions + 1 OBT sharing conformed dims |
| **ML models** | Written: XGBoost delay clf, XGBoost voyage reg, Isolation Forest anomaly |
| **FastAPI endpoints** | Written: 11 REST endpoints + 1 WebSocket + demo page |
| **Security guardrails** | Written: 17/17 safety tests (ask_data.py, 4 defense layers) |
| **Demo UI** | Written: Deck.gl dark-mode vessel map with KPIs, anomalies, Ask Your Data |

## First verification steps

```bash
# 1. Build the warehouse
python scripts/build_demo.py

# 2. Run ML experiments
python ml/run_experiments.py

# 3. Run safety tests (should be 17/17)
python tests/test_ask_data_safety.py

# 4. Start the API
uvicorn main:app --reload --app-dir serving/api
# Open http://localhost:8000/demo
```

## Not yet executed

| Component | First step |
|-----------|------------|
| **Digitraffic live polling** | Set DIGITRAFFIC_USER, run `python ingestion/ais/digitraffic_poller.py` |
| **Open-Meteo live fetch** | Run `python ingestion/weather/openmeteo_marine.py` (requires internet) |
| **MarineCadastre real data** | Download GeoParquet from marinecadastre.gov, run with `--file` flag |
| **Text-to-SQL end-to-end** | Set ANTHROPIC_API_KEY, call POST /ask |
| **AI Briefing** | Set ANTHROPIC_API_KEY, call POST /ai-briefing |
| **Docker Compose** | `docker compose up -d` |
| **dbt build** | `cd warehouse/dbt && dbt build --profiles-dir .` |
