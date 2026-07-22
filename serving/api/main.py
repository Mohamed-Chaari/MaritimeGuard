"""MaritimeGuard AI serving API.

The presentation layer: serves the gold-layer maritime marts, a live WebSocket
feed of vessel positions, a guarded natural language query endpoint, and an
AI-powered supply chain risk briefing generator.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

import duckdb
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ask_data import UnsafeSQLError, ask as ask_data_impl
from live import live_broadcaster, manager

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "../../warehouse/maritimeguard.duckdb")
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


def read_only_connection() -> duckdb.DuckDBPyConnection:
    """A fresh short-lived read-only connection per request — no shared
    mutable connection state, and no endpoint can ever write to the warehouse.
    """
    return duckdb.connect(DUCKDB_PATH, read_only=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(live_broadcaster(DUCKDB_PATH))
    yield
    task.cancel()


app = FastAPI(
    title="MaritimeGuard AI API",
    version="1.0.0",
    description="Maritime Intelligence & Supply Chain Risk Platform — "
                 "serves vessel tracking, port analytics, AIS anomalies, "
                 "ML predictions, and natural-language querying.",
    lifespan=lifespan,
)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "MaritimeGuard AI"}


@app.get("/demo")
def demo_page():
    """Dark-mode Deck.gl vessel map — usable before the full frontend exists."""
    path = os.path.join(static_dir, "demo.html")
    if not os.path.exists(path):
        raise HTTPException(404, "demo page not built yet")
    return FileResponse(path)


# --------------------------------------------------------------------------
# Maritime KPIs
# --------------------------------------------------------------------------

@app.get("/kpis")
def kpis():
    con = read_only_connection()
    try:
        pos = con.execute("SELECT count(*) FROM gold.fct_vessel_positions").fetchone()
        vessels = con.execute("SELECT count(*) FROM gold.dim_vessels").fetchone()
        ports = con.execute("SELECT count(*) FROM gold.dim_ports").fetchone()
        calls = con.execute("SELECT count(*) FROM gold.fct_port_calls").fetchone()
        anomalies = con.execute("SELECT count(*) FROM gold.fct_ais_anomalies").fetchone()
        avg_sog = con.execute("SELECT round(avg(sog), 1) FROM gold.fct_vessel_positions WHERE sog > 0").fetchone()
        return {
            "total_positions": pos[0],
            "unique_vessels": vessels[0],
            "ports_tracked": ports[0],
            "port_calls": calls[0],
            "ais_anomalies": anomalies[0],
            "avg_speed_kts": avg_sog[0] if avg_sog else None,
        }
    finally:
        con.close()


# --------------------------------------------------------------------------
# Vessel endpoints
# --------------------------------------------------------------------------

@app.get("/vessels/active")
def active_vessels(limit: int = 50):
    """Vessels with recent position data."""
    con = read_only_connection()
    try:
        rows = con.execute("""
            SELECT v.vessel_key, v.vessel_name, v.vessel_type_desc,
                   v.imo, v.length_m, v.total_pings,
                   v.first_seen, v.last_seen
            FROM gold.dim_vessels v
            ORDER BY v.last_seen DESC
            LIMIT ?
        """, [limit]).fetchall()
        return [{"mmsi": r[0], "name": r[1], "type": r[2], "imo": r[3],
                 "length_m": r[4], "total_pings": r[5],
                 "first_seen": str(r[6]), "last_seen": str(r[7])} for r in rows]
    finally:
        con.close()


@app.get("/vessels/{mmsi}")
def vessel_profile(mmsi: str):
    con = read_only_connection()
    try:
        vessel = con.execute("""
            SELECT vessel_key, vessel_name, vessel_type_desc, imo,
                   length_m, width_m, draft_m, call_sign, total_pings,
                   first_seen, last_seen
            FROM gold.dim_vessels WHERE vessel_key = ?
        """, [mmsi]).fetchone()
        if not vessel:
            raise HTTPException(404, f"vessel {mmsi} not found")

        # Latest position
        pos = con.execute("""
            SELECT latitude, longitude, sog, cog, heading, position_ts
            FROM gold.fct_vessel_positions
            WHERE vessel_key = ?
            ORDER BY position_ts DESC LIMIT 1
        """, [mmsi]).fetchone()

        # Anomaly count
        anom = con.execute("""
            SELECT count(*), round(avg(risk_score), 1)
            FROM gold.fct_ais_anomalies WHERE vessel_key = ?
        """, [mmsi]).fetchone()

        return {
            "mmsi": vessel[0], "name": vessel[1], "type": vessel[2],
            "imo": vessel[3], "length_m": vessel[4], "width_m": vessel[5],
            "draft_m": vessel[6], "call_sign": vessel[7],
            "total_pings": vessel[8],
            "first_seen": str(vessel[9]), "last_seen": str(vessel[10]),
            "latest_position": {
                "lat": pos[0], "lon": pos[1], "sog": pos[2],
                "cog": pos[3], "heading": pos[4], "ts": str(pos[5]),
            } if pos else None,
            "anomaly_count": anom[0] if anom else 0,
            "avg_risk_score": anom[1] if anom else None,
        }
    finally:
        con.close()


@app.get("/vessels/delays")
def delayed_vessels():
    """Vessels predicted to be delayed by the ML model."""
    con = read_only_connection()
    try:
        # Check if ML predictions exist
        tables = con.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'gold' AND table_name = 'vessel_delay_predictions'
        """).fetchone()
        if not tables:
            return {"message": "ML predictions not yet available. Run ml/run_experiments.py first.", "vessels": []}

        rows = con.execute("""
            SELECT vessel_key, port_key, duration_hours, delay_proba
            FROM gold.vessel_delay_predictions
            WHERE delay_proba > 0.5
            ORDER BY delay_proba DESC LIMIT 20
        """).fetchall()
        return [{"mmsi": r[0], "port_key": r[1], "duration_hours": round(r[2], 1),
                 "delay_probability": round(r[3], 4)} for r in rows]
    finally:
        con.close()


# --------------------------------------------------------------------------
# Port endpoints
# --------------------------------------------------------------------------

@app.get("/ports/top")
def top_ports(n: int = 10):
    con = read_only_connection()
    try:
        rows = con.execute("""
            SELECT dp.port_name, dp.country, dp.harbor_size, dp.capacity_tier,
                   count(*) as call_count
            FROM gold.fct_port_calls pc
            JOIN gold.dim_ports dp ON pc.port_key = dp.port_key
            GROUP BY 1, 2, 3, 4
            ORDER BY call_count DESC LIMIT ?
        """, [n]).fetchall()
        return [{"port": r[0], "country": r[1], "size": r[2],
                 "tier": r[3], "calls": r[4]} for r in rows]
    finally:
        con.close()


@app.get("/ports/{port_key}/congestion")
def port_congestion(port_key: int):
    con = read_only_connection()
    try:
        port = con.execute("""
            SELECT port_name, country, harbor_size, channel_depth_m, capacity_tier
            FROM gold.dim_ports WHERE port_key = ?
        """, [port_key]).fetchone()
        if not port:
            raise HTTPException(404, f"port {port_key} not found")

        stats = con.execute("""
            SELECT count(*) as total_calls,
                   round(avg(duration_hours), 1) as avg_stay_hours,
                   sum(case when is_extended_stay = 1 then 1 else 0 end) as extended_stays
            FROM gold.fct_port_calls WHERE port_key = ?
        """, [port_key]).fetchone()

        return {
            "port_name": port[0], "country": port[1], "size": port[2],
            "channel_depth_m": port[3], "capacity_tier": port[4],
            "total_calls": stats[0] if stats else 0,
            "avg_stay_hours": stats[1] if stats else None,
            "extended_stays": stats[2] if stats else 0,
        }
    finally:
        con.close()


# --------------------------------------------------------------------------
# AIS Anomalies
# --------------------------------------------------------------------------

@app.get("/anomalies/recent")
def recent_anomalies(limit: int = 20):
    con = read_only_connection()
    try:
        rows = con.execute("""
            SELECT vessel_key, anomaly_ts, anomaly_type, risk_score,
                   time_gap_minutes, distance_gap_nm, last_known_lat, last_known_lon
            FROM gold.fct_ais_anomalies
            ORDER BY anomaly_ts DESC LIMIT ?
        """, [limit]).fetchall()
        return [{"mmsi": r[0], "ts": str(r[1]), "type": r[2], "risk_score": r[3],
                 "gap_minutes": r[4], "distance_nm": r[5],
                 "lat": r[6], "lon": r[7]} for r in rows]
    finally:
        con.close()


# --------------------------------------------------------------------------
# Live WebSocket (vessel position stream)
# --------------------------------------------------------------------------

@app.websocket("/ws/live-vessels")
async def ws_live_vessels(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive; content unused
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# --------------------------------------------------------------------------
# Ask Your Data (natural language -> validated SQL -> answer)
# --------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str


@app.post("/ask")
def ask_your_data(req: AskRequest):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(
            500, "ANTHROPIC_API_KEY is not set. Add it to .env.")
    try:
        return ask_data_impl(req.question, DUCKDB_PATH, api_key=ANTHROPIC_API_KEY)
    except UnsafeSQLError as e:
        raise HTTPException(400, f"the generated query was rejected for safety: {e}")
    except TimeoutError as e:
        raise HTTPException(504, str(e))


# --------------------------------------------------------------------------
# AI Briefing (LLM-powered supply chain risk summary)
# --------------------------------------------------------------------------

class BriefingRequest(BaseModel):
    context: str = "general"  # "general", port name, or region


@app.post("/ai-briefing")
def ai_briefing(req: BriefingRequest):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY is not set.")
    try:
        from briefing import generate_briefing
        return generate_briefing(req.context, DUCKDB_PATH, api_key=ANTHROPIC_API_KEY)
    except Exception as e:
        raise HTTPException(500, str(e))
