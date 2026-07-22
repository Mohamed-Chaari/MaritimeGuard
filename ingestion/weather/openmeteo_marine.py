"""MaritimeGuard AI — Open-Meteo marine weather ingestion.

Fetches hourly marine weather data (wave height, ocean currents) and surface
wind data for major maritime chokepoints and shipping lanes. Stores in DuckDB
bronze layer for use as ML features and dashboard context.

APIs:
  - Marine: https://marine-api.open-meteo.com/v1/marine
  - Weather: https://api.open-meteo.com/v1/forecast
License: CC BY 4.0 (non-commercial free, no API key)
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import duckdb
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = str(PROJECT_ROOT / "warehouse" / "maritimeguard.duckdb")

# Major maritime chokepoints and shipping regions
CHOKEPOINTS = {
    "strait_of_gibraltar":  {"lat": 35.96, "lon": -5.60},
    "english_channel":      {"lat": 50.50, "lon": -1.00},
    "suez_canal_north":     {"lat": 31.27, "lon": 32.31},
    "strait_of_hormuz":     {"lat": 26.60, "lon": 56.25},
    "malacca_strait":       {"lat": 2.50,  "lon": 101.50},
    "cape_good_hope":       {"lat": -34.35, "lon": 18.50},
    "panama_canal_atlantic":{"lat": 9.38,  "lon": -79.92},
    "gulf_of_mexico_central":{"lat": 27.00, "lon": -90.00},
    "houston_ship_channel": {"lat": 29.50, "lon": -94.80},
    "new_orleans_approach": {"lat": 29.00, "lon": -89.50},
    "tampa_bay_approach":   {"lat": 27.60, "lon": -82.80},
    "corpus_christi_approach":{"lat": 27.70, "lon": -97.10},
}

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

MARINE_VARS = "wave_height,wave_direction,wave_period,wind_wave_height,swell_wave_height"
WEATHER_VARS = "wind_speed_10m,wind_direction_10m,wind_gusts_10m"


def fetch_zone_weather(zone_name: str, lat: float, lon: float,
                       past_days: int = 7, forecast_days: int = 3) -> pd.DataFrame:
    """Fetch combined marine + weather data for one zone."""
    # Marine data (waves, currents)
    marine_resp = requests.get(MARINE_URL, params={
        "latitude": lat, "longitude": lon,
        "hourly": MARINE_VARS,
        "past_days": past_days,
        "forecast_days": forecast_days,
        "timezone": "UTC",
    }, timeout=30)
    marine_resp.raise_for_status()
    marine = marine_resp.json()

    # Surface weather (wind)
    weather_resp = requests.get(WEATHER_URL, params={
        "latitude": lat, "longitude": lon,
        "hourly": WEATHER_VARS,
        "past_days": past_days,
        "forecast_days": forecast_days,
        "timezone": "UTC",
    }, timeout=30)
    weather_resp.raise_for_status()
    weather = weather_resp.json()

    # Merge on time
    marine_hourly = marine.get("hourly", {})
    weather_hourly = weather.get("hourly", {})

    times = marine_hourly.get("time", [])
    df = pd.DataFrame({
        "zone_name": zone_name,
        "latitude": lat,
        "longitude": lon,
        "timestamp_utc": pd.to_datetime(times, utc=True),
        "wave_height_m": marine_hourly.get("wave_height"),
        "wave_direction_deg": marine_hourly.get("wave_direction"),
        "wave_period_s": marine_hourly.get("wave_period"),
        "wind_wave_height_m": marine_hourly.get("wind_wave_height"),
        "swell_wave_height_m": marine_hourly.get("swell_wave_height"),
        "wind_speed_10m_kmh": weather_hourly.get("wind_speed_10m"),
        "wind_direction_10m_deg": weather_hourly.get("wind_direction_10m"),
        "wind_gusts_10m_kmh": weather_hourly.get("wind_gusts_10m"),
    })
    return df


def load_weather(db_path: str, past_days: int = 7, forecast_days: int = 3) -> int:
    """Fetch weather for all chokepoints and load into bronze."""
    all_dfs = []
    for zone_name, coords in CHOKEPOINTS.items():
        print(f"  Fetching {zone_name} ({coords['lat']}, {coords['lon']})...")
        try:
            df = fetch_zone_weather(zone_name, coords["lat"], coords["lon"],
                                    past_days, forecast_days)
            all_dfs.append(df)
        except Exception as e:
            print(f"    WARNING: {zone_name} failed: {e}")
        time.sleep(0.5)  # respect rate limits

    if not all_dfs:
        print("No weather data fetched!")
        return 0

    combined = pd.concat(all_dfs, ignore_index=True)

    con = duckdb.connect(db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    con.execute("DROP TABLE IF EXISTS bronze.raw_marine_weather")
    con.execute("""
        CREATE TABLE bronze.raw_marine_weather AS
        SELECT * FROM combined
    """)
    count = con.execute("SELECT count(*) FROM bronze.raw_marine_weather").fetchone()[0]
    con.close()
    return count


def main():
    parser = argparse.ArgumentParser(description="Fetch marine weather for chokepoints")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--past-days", type=int, default=7)
    parser.add_argument("--forecast-days", type=int, default=3)
    args = parser.parse_args()

    print("Fetching marine weather data from Open-Meteo...")
    count = load_weather(args.db, args.past_days, args.forecast_days)
    print(f"-> bronze.raw_marine_weather: {count:,} rows loaded")


if __name__ == "__main__":
    main()
