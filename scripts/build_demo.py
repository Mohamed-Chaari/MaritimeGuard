"""MaritimeGuard AI — end-to-end build script.

Builds the entire warehouse from scratch:
  1. Generates/loads AIS position data (Gulf of Mexico sample)
  2. Loads World Port Index
  3. Generates marine weather data
  4. Runs dbt to build bronze → silver → gold
  5. Prints maritime KPIs for verification

Usage:
    python scripts/build_demo.py              # full build with sample data
    python scripts/build_demo.py --skip-dbt   # only load bronze, skip dbt
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import duckdb

DB_PATH = str(PROJECT_ROOT / "warehouse" / "maritimeguard.duckdb")
DBT_DIR = str(PROJECT_ROOT / "warehouse" / "dbt")


def banner(text: str) -> None:
    print("\n" + "=" * 64 + f"\n{text}\n" + "=" * 64)


def step_1_ais():
    """Load AIS vessel position data into bronze."""
    banner("1. AIS VESSEL POSITIONS")
    from ingestion.ais.marinecadastre_loader import generate_realistic_sample, load_dataframe
    df = generate_realistic_sample(n=50_000)
    count = load_dataframe(DB_PATH, df)
    print(f"-> bronze.raw_vessel_positions: {count:,} rows")


def step_2_ports():
    """Load World Port Index into bronze."""
    banner("2. WORLD PORT INDEX")
    from ingestion.ports.wpi_loader import generate_wpi_sample, load_dataframe
    df = generate_wpi_sample(n=120)
    count = load_dataframe(DB_PATH, df)
    print(f"-> bronze.raw_ports: {count:,} ports")


def step_3_weather():
    """Generate marine weather sample (offline-safe, no API call)."""
    banner("3. MARINE WEATHER")
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    zones = [
        "strait_of_gibraltar", "english_channel", "gulf_of_mexico_central",
        "houston_ship_channel", "new_orleans_approach", "tampa_bay_approach",
    ]
    coords = {
        "strait_of_gibraltar": (35.96, -5.60),
        "english_channel": (50.50, -1.00),
        "gulf_of_mexico_central": (27.00, -90.00),
        "houston_ship_channel": (29.50, -94.80),
        "new_orleans_approach": (29.00, -89.50),
        "tampa_bay_approach": (27.60, -82.80),
    }

    records = []
    base = pd.Timestamp("2024-06-01", tz="UTC")
    for zone in zones:
        lat, lon = coords[zone]
        for h in range(240):  # 10 days of hourly data
            ts = base + pd.Timedelta(hours=h)
            records.append({
                "zone_name": zone,
                "latitude": lat,
                "longitude": lon,
                "timestamp_utc": ts,
                "wave_height_m": round(max(0, rng.normal(1.5, 0.8)), 2),
                "wave_direction_deg": round(rng.uniform(0, 360), 1),
                "wave_period_s": round(max(2, rng.normal(7, 2)), 1),
                "wind_wave_height_m": round(max(0, rng.normal(1.0, 0.5)), 2),
                "swell_wave_height_m": round(max(0, rng.normal(0.8, 0.4)), 2),
                "wind_speed_10m_kmh": round(max(0, rng.normal(20, 10)), 1),
                "wind_direction_10m_deg": round(rng.uniform(0, 360), 1),
                "wind_gusts_10m_kmh": round(max(0, rng.normal(30, 12)), 1),
            })

    df = pd.DataFrame(records)
    con = duckdb.connect(DB_PATH)
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    con.execute("DROP TABLE IF EXISTS bronze.raw_marine_weather")
    con.execute("CREATE TABLE bronze.raw_marine_weather AS SELECT * FROM df")
    count = con.execute("SELECT count(*) FROM bronze.raw_marine_weather").fetchone()[0]
    con.close()
    print(f"-> bronze.raw_marine_weather: {count:,} rows (6 zones × 240 hours)")


def step_4_dbt():
    """Run dbt build (snapshot + models + tests)."""
    banner("4. dbt BUILD (bronze → silver → gold)")
    dbt_bin = os.path.join(os.path.dirname(sys.executable), 'dbt')
    if not os.path.exists(dbt_bin):
        dbt_bin = "dbt"  # Fallback to system path

    result = subprocess.run(
        [dbt_bin, "build", "--profiles-dir", "."],
        cwd=DBT_DIR,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode != 0:
        print("WARNING: dbt build returned non-zero exit code")
        return False
    return True


def step_5_kpis():
    """Print maritime KPIs from the gold layer."""
    banner("5. MARITIME KPIs")
    con = duckdb.connect(DB_PATH, read_only=True)

    def q(sql):
        try:
            return con.execute(sql).fetchone()
        except Exception:
            return None

    kpis = {
        "Vessel positions": q("SELECT count(*) FROM gold.fct_vessel_positions"),
        "Unique vessels":   q("SELECT count(*) FROM gold.dim_vessels"),
        "Ports loaded":     q("SELECT count(*) FROM gold.dim_ports"),
        "Port calls":       q("SELECT count(*) FROM gold.fct_port_calls"),
        "AIS anomalies":    q("SELECT count(*) FROM gold.fct_ais_anomalies"),
        "Time dimension":   q("SELECT count(*) FROM gold.dim_time"),
        "Weather zones":    q("SELECT count(*) FROM gold.dim_weather_zones"),
        "OBT rows":         q("SELECT count(*) FROM gold.obt_vessel_tracking"),
    }

    for label, row in kpis.items():
        val = f"{row[0]:,}" if row else "NOT BUILT"
        print(f"  {label:24} {val}")

    # Top vessel types
    top = con.execute("""
        SELECT vessel_type_desc, count(*) n
        FROM gold.dim_vessels GROUP BY 1 ORDER BY n DESC LIMIT 5
    """).fetchall() if q("SELECT 1 FROM gold.dim_vessels LIMIT 1") else []

    if top:
        print("\nTop vessel types:")
        for desc, n in top:
            print(f"  {desc:24} {n:>6}")

    # Anomaly summary
    anomalies = con.execute("""
        SELECT anomaly_type, count(*) n, round(avg(risk_score), 1) avg_risk
        FROM gold.fct_ais_anomalies GROUP BY 1 ORDER BY n DESC
    """).fetchall() if q("SELECT 1 FROM gold.fct_ais_anomalies LIMIT 1") else []

    if anomalies:
        print("\nAIS anomalies by type:")
        for atype, n, risk in anomalies:
            print(f"  {atype:28} count={n:>4}  avg_risk={risk}")

    con.close()


def main():
    parser = argparse.ArgumentParser(description="MaritimeGuard AI — build demo warehouse")
    parser.add_argument("--skip-dbt", action="store_true", help="Only load bronze data")
    args = parser.parse_args()

    # Remove old database if exists
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Removed old {DB_PATH}")

    step_1_ais()
    step_2_ports()
    step_3_weather()

    if not args.skip_dbt:
        step_4_dbt()

    step_5_kpis()
    print("\n" + "=" * 64 + "\nBUILD COMPLETE\n" + "=" * 64)


if __name__ == "__main__":
    main()
