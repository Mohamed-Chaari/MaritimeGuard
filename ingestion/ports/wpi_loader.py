"""MaritimeGuard AI — NGA World Port Index loader.

Loads the World Port Index (NGA Publication 150) into DuckDB bronze layer.
Contains ~3,700 ports worldwide with coordinates, facilities, depths, and
capacity data. Used as dim_ports in the gold layer.

Source: National Geospatial-Intelligence Agency (NGA)
License: Public domain (US Government work, Title 17 U.S.C. §105)
Download: https://msi.nga.mil/ or Kaggle
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = str(PROJECT_ROOT / "warehouse" / "maritimeguard.duckdb")
WPI_DIR = str(PROJECT_ROOT / "data" / "wpi")


def generate_wpi_sample(n: int = 120, seed: int = 42) -> pd.DataFrame:
    """Generate a representative WPI sample covering key maritime ports.

    Includes real port names and approximate coordinates for the world's
    busiest ports, plus generated entries for coverage.
    """
    rng = np.random.default_rng(seed)

    # Real major ports (name, country, lat, lon, harbor_size, channel_depth_m)
    real_ports = [
        # Gulf of Mexico / US South
        ("Houston", "United States", 29.76, -95.09, "Large", 14.0),
        ("New Orleans", "United States", 29.95, -90.07, "Large", 13.7),
        ("Corpus Christi", "United States", 27.80, -97.40, "Large", 14.3),
        ("Tampa", "United States", 27.95, -82.46, "Large", 12.8),
        ("Mobile", "United States", 30.69, -88.04, "Medium", 13.7),
        ("Galveston", "United States", 29.30, -94.79, "Medium", 12.2),
        ("Pensacola", "United States", 30.41, -87.21, "Small", 10.1),
        ("Key West", "United States", 24.56, -81.78, "Small", 6.4),
        ("Port Fourchon", "United States", 29.11, -90.20, "Medium", 7.3),
        ("Freeport TX", "United States", 28.94, -95.36, "Medium", 13.7),
        # US East Coast
        ("New York/New Jersey", "United States", 40.68, -74.04, "Large", 15.2),
        ("Savannah", "United States", 32.08, -81.09, "Large", 14.0),
        ("Norfolk", "United States", 36.85, -76.30, "Large", 15.2),
        ("Charleston", "United States", 32.78, -79.93, "Large", 14.3),
        ("Miami", "United States", 25.77, -80.17, "Large", 11.0),
        # US West Coast
        ("Los Angeles", "United States", 33.74, -118.27, "Large", 16.2),
        ("Long Beach", "United States", 33.76, -118.19, "Large", 16.8),
        ("Seattle", "United States", 47.58, -122.35, "Large", 15.5),
        # Europe
        ("Rotterdam", "Netherlands", 51.90, 4.50, "Large", 24.0),
        ("Antwerp", "Belgium", 51.23, 4.42, "Large", 16.0),
        ("Hamburg", "Germany", 53.54, 9.97, "Large", 16.0),
        ("Felixstowe", "United Kingdom", 51.96, 1.35, "Large", 15.0),
        ("Le Havre", "France", 49.49, 0.11, "Large", 16.0),
        ("Piraeus", "Greece", 37.94, 23.64, "Large", 18.0),
        ("Algeciras", "Spain", 36.13, -5.44, "Large", 16.0),
        # Asia
        ("Shanghai", "China", 31.23, 121.47, "Large", 16.0),
        ("Singapore", "Singapore", 1.26, 103.84, "Large", 20.0),
        ("Busan", "South Korea", 35.10, 129.03, "Large", 16.0),
        # Middle East
        ("Jebel Ali", "United Arab Emirates", 25.01, 55.06, "Large", 17.0),
        ("Jeddah", "Saudi Arabia", 21.49, 39.17, "Large", 16.0),
        # Caribbean / Central America
        ("Colon", "Panama", 9.36, -79.90, "Large", 13.0),
        ("Kingston", "Jamaica", 17.97, -76.84, "Medium", 12.8),
        # Africa
        ("Durban", "South Africa", -29.87, 31.03, "Large", 12.8),
        ("Lagos/Apapa", "Nigeria", 6.43, 3.39, "Medium", 10.0),
    ]

    # Build the real ports first
    records = []
    for i, (name, country, lat, lon, size, depth) in enumerate(real_ports):
        records.append({
            "port_index": i + 1,
            "port_name": name,
            "country": country,
            "latitude": lat,
            "longitude": lon,
            "harbor_size": size,
            "harbor_type": rng.choice(["Coastal Natural", "Coastal Breakwater",
                                       "River Basin", "River Natural"]),
            "shelter_quality": rng.choice(["Excellent", "Good", "Fair"]),
            "channel_depth_m": depth,
            "anchorage_depth_m": round(depth - rng.uniform(1, 3), 1),
            "cargo_pier_depth_m": round(depth - rng.uniform(0.5, 2), 1),
            "has_dry_dock": rng.choice(["Yes", "No"], p=[0.6, 0.4]),
            "has_railway": rng.choice(["Yes", "No"], p=[0.7, 0.3]),
            "has_provisions": "Yes",
            "has_fuel_oil": "Yes",
            "max_vessel_length_m": int(rng.choice([200, 300, 350, 400])),
            "tide_range_m": round(rng.uniform(0.5, 6.0), 1),
        })

    # Fill remaining with generated ports
    countries = ["Brazil", "Argentina", "Mexico", "India", "Japan", "Australia",
                 "Egypt", "Morocco", "Italy", "Norway", "Sweden", "Finland",
                 "Philippines", "Vietnam", "Thailand", "Indonesia"]
    for i in range(len(real_ports), n):
        country = rng.choice(countries)
        records.append({
            "port_index": i + 1,
            "port_name": f"Port_{country[:3].upper()}_{i:03d}",
            "country": country,
            "latitude": round(rng.uniform(-40, 65), 4),
            "longitude": round(rng.uniform(-120, 150), 4),
            "harbor_size": rng.choice(["Large", "Medium", "Small", "Very Small"],
                                      p=[0.15, 0.30, 0.35, 0.20]),
            "harbor_type": rng.choice(["Coastal Natural", "Coastal Breakwater",
                                       "River Basin", "River Natural"]),
            "shelter_quality": rng.choice(["Excellent", "Good", "Fair", "Poor"],
                                          p=[0.2, 0.4, 0.3, 0.1]),
            "channel_depth_m": round(rng.uniform(3, 20), 1),
            "anchorage_depth_m": round(rng.uniform(3, 18), 1),
            "cargo_pier_depth_m": round(rng.uniform(3, 16), 1),
            "has_dry_dock": rng.choice(["Yes", "No"], p=[0.3, 0.7]),
            "has_railway": rng.choice(["Yes", "No"], p=[0.4, 0.6]),
            "has_provisions": rng.choice(["Yes", "No"], p=[0.7, 0.3]),
            "has_fuel_oil": rng.choice(["Yes", "No"], p=[0.8, 0.2]),
            "max_vessel_length_m": int(rng.choice([100, 150, 200, 300, 400])),
            "tide_range_m": round(rng.uniform(0.3, 8.0), 1),
        })

    return pd.DataFrame(records[:n])


def load_csv(db_path: str, csv_path: str) -> int:
    """Load a WPI CSV into bronze.raw_ports."""
    con = duckdb.connect(db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    con.execute(f"""
        CREATE OR REPLACE TABLE bronze.raw_ports AS
        SELECT * FROM read_csv_auto('{csv_path}', header=true)
    """)
    count = con.execute("SELECT count(*) FROM bronze.raw_ports").fetchone()[0]
    con.close()
    return count


def load_dataframe(db_path: str, df: pd.DataFrame) -> int:
    """Load a DataFrame into bronze.raw_ports."""
    con = duckdb.connect(db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    con.execute("CREATE OR REPLACE TABLE bronze.raw_ports AS SELECT * FROM df")
    count = con.execute("SELECT count(*) FROM bronze.raw_ports").fetchone()[0]
    con.close()
    return count


def main():
    parser = argparse.ArgumentParser(description="Load World Port Index into DuckDB")
    parser.add_argument("--file", help="Path to WPI CSV file")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--generate-sample", action="store_true",
                        help="Generate a representative port sample")
    args = parser.parse_args()

    if args.file:
        print(f"Loading WPI from {args.file}...")
        count = load_csv(args.db, args.file)
    elif args.generate_sample:
        print("Generating representative port sample...")
        df = generate_wpi_sample()
        count = load_dataframe(args.db, df)
    else:
        # Check for CSV in data/wpi/
        wpi_dir = Path(WPI_DIR)
        csvs = list(wpi_dir.glob("*.csv"))
        if csvs:
            print(f"Loading {csvs[0].name}...")
            count = load_csv(args.db, str(csvs[0]))
        else:
            print("No WPI CSV found. Generating sample...")
            df = generate_wpi_sample()
            count = load_dataframe(args.db, df)

    print(f"-> bronze.raw_ports: {count:,} ports loaded")


if __name__ == "__main__":
    main()
