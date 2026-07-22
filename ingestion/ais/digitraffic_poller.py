"""MaritimeGuard AI — Digitraffic.fi real-time AIS poller.

Polls the Finnish Transport Infrastructure Agency's open AIS API for live
vessel positions in the Baltic Sea. Appends new positions to the DuckDB
bronze layer on each poll cycle.

API: https://meri.digitraffic.fi/api/ais/v1/locations
Docs: https://www.digitraffic.fi/en/marine-traffic/
License: CC BY 4.0 (attribution required: Fintraffic / digitraffic.fi)
Rate limit: 60 req/min unauthenticated, higher with Digitraffic-User header.

Usage:
    python ingestion/ais/digitraffic_poller.py                # poll once
    python ingestion/ais/digitraffic_poller.py --continuous    # poll every 30s
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import duckdb
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = str(PROJECT_ROOT / "warehouse" / "maritimeguard.duckdb")

AIS_URL = "https://meri.digitraffic.fi/api/ais/v1/locations"
HEADERS = {
    "Accept": "application/json",
    "Digitraffic-User": os.getenv("DIGITRAFFIC_USER", "MaritimeGuardAI"),
}


def fetch_locations() -> list[dict]:
    """Fetch current vessel locations from Digitraffic API."""
    resp = requests.get(AIS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # The response has a "features" array (GeoJSON FeatureCollection)
    features = data.get("features", [])
    records = []
    for f in features:
        props = f.get("properties", {})
        coords = f.get("geometry", {}).get("coordinates", [None, None])
        records.append({
            "MMSI": str(props.get("mmsi", "")),
            "BaseDateTime": props.get("timestampExternal", props.get("timestamp", "")),
            "LAT": coords[1] if len(coords) > 1 else None,
            "LON": coords[0] if len(coords) > 0 else None,
            "SOG": props.get("sog"),
            "COG": props.get("cog"),
            "Heading": props.get("heading"),
            "VesselName": None,   # Digitraffic location API doesn't include name
            "IMO": None,
            "CallSign": None,
            "VesselType": props.get("shipType"),
            "Status": props.get("navStat"),
            "Length": None,
            "Width": None,
            "Draft": props.get("draught"),
            "Cargo": None,
            "TransceiverClass": None,
        })
    return records


def append_to_bronze(db_path: str, records: list[dict]) -> int:
    """Append fetched records to bronze.raw_vessel_positions."""
    if not records:
        return 0

    import pandas as pd
    df = pd.DataFrame(records)

    con = duckdb.connect(db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")

    # Create table if not exists (same schema as marinecadastre_loader)
    con.execute("""
        CREATE TABLE IF NOT EXISTS bronze.raw_vessel_positions (
            MMSI             VARCHAR,
            BaseDateTime     TIMESTAMP,
            LAT              DOUBLE,
            LON              DOUBLE,
            SOG              DOUBLE,
            COG              DOUBLE,
            Heading          DOUBLE,
            VesselName       VARCHAR,
            IMO              VARCHAR,
            CallSign         VARCHAR,
            VesselType       INTEGER,
            Status           INTEGER,
            Length            DOUBLE,
            Width            DOUBLE,
            Draft            DOUBLE,
            Cargo            VARCHAR,
            TransceiverClass VARCHAR
        )
    """)

    con.execute("""
        INSERT INTO bronze.raw_vessel_positions
        SELECT
            CAST(MMSI AS VARCHAR),
            CAST(BaseDateTime AS TIMESTAMP),
            CAST(LAT AS DOUBLE),
            CAST(LON AS DOUBLE),
            CAST(SOG AS DOUBLE),
            CAST(COG AS DOUBLE),
            CAST(Heading AS DOUBLE),
            CAST(VesselName AS VARCHAR),
            CAST(IMO AS VARCHAR),
            CAST(CallSign AS VARCHAR),
            CAST(VesselType AS INTEGER),
            CAST(Status AS INTEGER),
            CAST(Length AS DOUBLE),
            CAST(Width AS DOUBLE),
            CAST(Draft AS DOUBLE),
            CAST(Cargo AS VARCHAR),
            CAST(TransceiverClass AS VARCHAR)
        FROM df
    """)

    total = con.execute("SELECT count(*) FROM bronze.raw_vessel_positions").fetchone()[0]
    con.close()
    return len(records)


def main():
    parser = argparse.ArgumentParser(description="Poll Digitraffic AIS API")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--continuous", action="store_true",
                        help="Poll continuously every --interval seconds")
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args()

    if args.continuous:
        print(f"Continuous polling every {args.interval}s — Ctrl+C to stop")
        while True:
            try:
                records = fetch_locations()
                n = append_to_bronze(args.db, records)
                print(f"  [{time.strftime('%H:%M:%S')}] +{n} vessel positions ingested")
            except Exception as e:
                print(f"  [{time.strftime('%H:%M:%S')}] error: {e}")
            time.sleep(args.interval)
    else:
        print("Fetching Digitraffic AIS locations...")
        records = fetch_locations()
        n = append_to_bronze(args.db, records)
        print(f"-> {n} vessel positions appended to bronze.raw_vessel_positions")


if __name__ == "__main__":
    main()
