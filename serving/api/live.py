"""MaritimeGuard AI — live vessel position stream over WebSocket.

Polls the warehouse for recent vessel positions and broadcasts them to all
connected clients. Each broadcast opens its own short-lived read-only
connection — the live layer can never write to the warehouse, even by accident.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import duckdb
from fastapi import WebSocket


class ConnectionManager:
    """Tracks connected WebSocket clients and fans out broadcasts to them."""

    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


async def live_broadcaster(db_path: str, interval: int = 5) -> None:
    """Background task: every `interval` seconds, push a vessel position tick.

    Skips the database round-trip entirely when nobody is connected, so an
    idle demo does not spin the CPU or hammer the warehouse file.
    """
    while True:
        await asyncio.sleep(interval)
        if not manager.active:
            continue
        try:
            con = duckdb.connect(db_path, read_only=True)

            # Get latest position for each vessel (top 100 by recency)
            vessels = con.execute("""
                WITH latest AS (
                    SELECT vessel_key, latitude, longitude, sog, cog, heading,
                           position_ts,
                           row_number() OVER (PARTITION BY vessel_key
                                              ORDER BY position_ts DESC) as rn
                    FROM gold.fct_vessel_positions
                )
                SELECT l.vessel_key, l.latitude, l.longitude, l.sog, l.cog,
                       l.heading, l.position_ts,
                       dv.vessel_name, dv.vessel_type_desc
                FROM latest l
                LEFT JOIN gold.dim_vessels dv ON l.vessel_key = dv.vessel_key
                WHERE l.rn = 1
                ORDER BY l.position_ts DESC
                LIMIT 100
            """).fetchall()

            # Get anomaly count
            anomaly_count = con.execute(
                "SELECT count(*) FROM gold.fct_ais_anomalies"
            ).fetchone()[0]

            # Get total stats
            total_vessels = con.execute(
                "SELECT count(*) FROM gold.dim_vessels"
            ).fetchone()[0]

            con.close()
        except duckdb.Error:
            continue

        await manager.broadcast({
            "type": "vessel_tick",
            "vessels": [
                {
                    "mmsi": v[0], "lat": v[1], "lon": v[2],
                    "sog": v[3], "cog": v[4], "heading": v[5],
                    "ts": str(v[6]),
                    "name": v[7], "type": v[8],
                }
                for v in vessels
            ],
            "total_vessels": total_vessels,
            "anomaly_count": anomaly_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
