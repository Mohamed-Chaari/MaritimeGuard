"""MaritimeGuard AI — MarineCadastre AIS bulk loader.

Downloads and loads historical AIS vessel position data from NOAA's
MarineCadastre.gov into the DuckDB bronze layer. The data is provided as
GeoParquet files, which DuckDB reads natively — zero pandas overhead.

Usage:
    python ingestion/ais/marinecadastre_loader.py                     # load sample
    python ingestion/ais/marinecadastre_loader.py --file path/to.parquet  # load specific file
    python ingestion/ais/marinecadastre_loader.py --generate-sample   # generate realistic sample

Data source: https://marinecadastre.gov/ais/
License: Public domain (US Government work)
Schema (2018–2024): MMSI, BaseDateTime, LAT, LON, SOG, COG, Heading,
    VesselName, IMO, CallSign, VesselType, Status, Length, Width, Draft,
    Cargo, TransceiverClass
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# Project root is three levels up from this file
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = str(PROJECT_ROOT / "warehouse" / "maritimeguard.duckdb")
AIS_DIR = str(PROJECT_ROOT / "data" / "ais_raw")


def generate_realistic_sample(n: int = 50_000, seed: int = 42) -> pd.DataFrame:
    """Generate a realistic AIS sample for the Gulf of Mexico region.

    Uses realistic vessel movement patterns: clusters around major ports
    (Houston, New Orleans, Tampa, Mobile, Corpus Christi), realistic speed
    distributions by vessel type, and proper coordinate ranges.
    """
    rng = np.random.default_rng(seed)

    # Major Gulf of Mexico ports (lat, lon)
    ports = {
        "Houston":       (29.76, -95.09),
        "New Orleans":   (29.95, -90.07),
        "Tampa":         (27.95, -82.46),
        "Mobile":        (30.69, -88.04),
        "Corpus Christi": (27.80, -97.40),
        "Galveston":     (29.30, -94.79),
        "Pensacola":     (30.41, -87.21),
        "Key West":      (24.56, -81.78),
    }
    port_names = list(ports.keys())
    port_coords = np.array(list(ports.values()))

    # Vessel types (AIS type codes)
    vessel_types = {
        70: ("Cargo",       8.0, 3.0,  180, 30, 8.0),   # type, avg_sog, std, length, width, draft
        80: ("Tanker",      7.5, 2.5,  220, 35, 12.0),
        60: ("Passenger",  14.0, 4.0,  250, 32, 7.0),
        30: ("Fishing",     4.0, 2.0,   25, 8,  3.0),
        52: ("Tug",         6.0, 2.5,   30, 10, 4.5),
        36: ("Sailing",     5.0, 3.0,   15, 5,  2.0),
        40: ("HSC",        25.0, 5.0,   45, 12, 3.0),
    }

    # Generate vessels
    n_vessels = 200
    mmsis = rng.integers(200000000, 799999999, size=n_vessels)
    imos = [f"IMO{rng.integers(1000000, 9999999)}" for _ in range(n_vessels)]
    vessel_type_codes = rng.choice(list(vessel_types.keys()), size=n_vessels,
                                   p=[0.30, 0.25, 0.10, 0.15, 0.10, 0.05, 0.05])
    vessel_names = [f"{vessel_types[vt][0]}_{i:03d}" for i, vt in enumerate(vessel_type_codes)]

    # Generate positions over 30 days (hourly-ish pings)
    base_time = pd.Timestamp("2024-06-01", tz="UTC")
    records = []

    for v_idx in range(n_vessels):
        vt = vessel_type_codes[v_idx]
        _, avg_sog, std_sog, length, width, draft = vessel_types[vt]

        # Each vessel gets a random number of pings (simulating voyages)
        n_pings = rng.integers(100, 500)

        # Start near a random port
        start_port_idx = rng.integers(0, len(port_names))
        lat = port_coords[start_port_idx, 0] + rng.normal(0, 0.5)
        lon = port_coords[start_port_idx, 1] + rng.normal(0, 0.5)

        # Random start time within the 30-day window
        start_offset_hours = rng.integers(0, 720)  # 30 days
        ts = base_time + pd.Timedelta(hours=int(start_offset_hours))

        for ping in range(n_pings):
            if len(records) >= n:
                break

            sog = max(0, rng.normal(avg_sog, std_sog))
            cog = rng.uniform(0, 360)
            heading = (cog + rng.normal(0, 5)) % 360

            # Navigation status: 0=under way, 1=at anchor, 5=moored
            if sog < 0.5:
                status = rng.choice([1, 5], p=[0.4, 0.6])
            else:
                status = 0

            # Occasionally create AIS blackouts (gaps) for anomaly detection
            if rng.random() < 0.02:  # 2% chance of blackout
                gap_hours = rng.integers(2, 48)
                ts += pd.Timedelta(hours=int(gap_hours))
                # Jump position (suspicious)
                lat += rng.normal(0, 2.0)
                lon += rng.normal(0, 2.0)
            else:
                ts += pd.Timedelta(minutes=int(rng.integers(5, 30)))

            # Move based on speed and course
            lat += (sog * 0.016667 / 60) * np.cos(np.radians(cog))  # rough nm to degrees
            lon += (sog * 0.016667 / 60) * np.sin(np.radians(cog)) / np.cos(np.radians(lat))

            # Clamp to Gulf of Mexico region
            lat = np.clip(lat, 18.0, 31.0)
            lon = np.clip(lon, -98.0, -80.0)

            records.append({
                "MMSI": str(mmsis[v_idx]),
                "BaseDateTime": ts.strftime("%Y-%m-%dT%H:%M:%S"),
                "LAT": round(lat, 6),
                "LON": round(lon, 6),
                "SOG": round(sog, 1),
                "COG": round(cog, 1),
                "Heading": round(heading, 1),
                "VesselName": vessel_names[v_idx],
                "IMO": imos[v_idx],
                "CallSign": f"WD{rng.integers(1000, 9999)}",
                "VesselType": int(vt),
                "Status": int(status),
                "Length": float(length + rng.normal(0, 5)),
                "Width": float(width + rng.normal(0, 2)),
                "Draft": round(float(max(1.0, draft + rng.normal(0, 1))), 1),
                "Cargo": str(rng.integers(0, 99)),
                "TransceiverClass": rng.choice(["A", "B"], p=[0.85, 0.15]),
            })

        if len(records) >= n:
            break

    return pd.DataFrame(records[:n])


def load_parquet(db_path: str, parquet_path: str) -> int:
    """Load a GeoParquet/Parquet file into bronze.raw_vessel_positions."""
    con = duckdb.connect(db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")

    # DuckDB reads parquet natively — this is the fastest path
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS bronze.raw_vessel_positions (
            MMSI            VARCHAR,
            BaseDateTime    TIMESTAMP,
            LAT             DOUBLE,
            LON             DOUBLE,
            SOG             DOUBLE,
            COG             DOUBLE,
            Heading         DOUBLE,
            VesselName      VARCHAR,
            IMO             VARCHAR,
            CallSign        VARCHAR,
            VesselType      INTEGER,
            Status          INTEGER,
            Length           DOUBLE,
            Width            DOUBLE,
            Draft            DOUBLE,
            Cargo           VARCHAR,
            TransceiverClass VARCHAR
        )
    """)

    con.execute(f"""
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
        FROM read_parquet('{parquet_path}')
    """)

    count = con.execute("SELECT count(*) FROM bronze.raw_vessel_positions").fetchone()[0]
    con.close()
    return count


def load_dataframe(db_path: str, df: pd.DataFrame) -> int:
    """Load a DataFrame into bronze.raw_vessel_positions."""
    con = duckdb.connect(db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    con.execute("DROP TABLE IF EXISTS bronze.raw_vessel_positions")
    con.execute("""
        CREATE TABLE bronze.raw_vessel_positions AS
        SELECT
            CAST(MMSI AS VARCHAR)            AS MMSI,
            CAST(BaseDateTime AS TIMESTAMP)  AS BaseDateTime,
            CAST(LAT AS DOUBLE)              AS LAT,
            CAST(LON AS DOUBLE)              AS LON,
            CAST(SOG AS DOUBLE)              AS SOG,
            CAST(COG AS DOUBLE)              AS COG,
            CAST(Heading AS DOUBLE)          AS Heading,
            CAST(VesselName AS VARCHAR)      AS VesselName,
            CAST(IMO AS VARCHAR)             AS IMO,
            CAST(CallSign AS VARCHAR)        AS CallSign,
            CAST(VesselType AS INTEGER)      AS VesselType,
            CAST(Status AS INTEGER)          AS Status,
            CAST(Length AS DOUBLE)            AS Length,
            CAST(Width AS DOUBLE)            AS Width,
            CAST(Draft AS DOUBLE)            AS Draft,
            CAST(Cargo AS VARCHAR)           AS Cargo,
            CAST(TransceiverClass AS VARCHAR) AS TransceiverClass
        FROM df
    """)
    count = con.execute("SELECT count(*) FROM bronze.raw_vessel_positions").fetchone()[0]
    con.close()
    return count


def main():
    parser = argparse.ArgumentParser(description="Load AIS data into MaritimeGuard DuckDB")
    parser.add_argument("--file", help="Path to a GeoParquet/Parquet AIS file")
    parser.add_argument("--db", default=DEFAULT_DB, help="DuckDB path")
    parser.add_argument("--generate-sample", action="store_true",
                        help="Generate a realistic Gulf of Mexico AIS sample")
    parser.add_argument("--n", type=int, default=50_000, help="Sample size (with --generate-sample)")
    args = parser.parse_args()

    if args.generate_sample:
        print(f"Generating {args.n:,} realistic AIS positions (Gulf of Mexico)...")
        df = generate_realistic_sample(n=args.n)
        count = load_dataframe(args.db, df)
        print(f"-> bronze.raw_vessel_positions: {count:,} rows loaded")
    elif args.file:
        print(f"Loading {args.file}...")
        count = load_parquet(args.db, args.file)
        print(f"-> bronze.raw_vessel_positions: {count:,} rows loaded")
    else:
        # Check for any parquet files in the data directory
        ais_dir = Path(AIS_DIR)
        parquets = list(ais_dir.glob("*.parquet")) + list(ais_dir.glob("*.geoparquet"))
        if parquets:
            for pf in parquets:
                print(f"Loading {pf.name}...")
                count = load_parquet(args.db, str(pf))
                print(f"  -> {count:,} total rows")
        else:
            print("No parquet files found. Generating sample data...")
            df = generate_realistic_sample(n=args.n)
            count = load_dataframe(args.db, df)
            print(f"-> bronze.raw_vessel_positions: {count:,} rows loaded")


if __name__ == "__main__":
    main()
