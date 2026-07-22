# Data Profiling: MaritimeGuard AI

## 1. MarineCadastre.gov (Historical AIS)
- **Volume:** ~50,000 pings processed in the sample.
- **Velocity:** Daily snapshots of historical tracking.
- **Quality Issues:** 
  - AIS receivers default to `(0, 0)` coordinates when GPS is lost (Null Island). We explicitly filter `LAT != 0` and `LON != 0` in `stg_vessel_positions`.
  - Spurious velocity readings (e.g. `SOG > 102.3`). Filtered in testing.

## 2. NGA World Port Index
- **Volume:** 3,700 global ports (filtered to 120 in sample).
- **Quality Issues:** 
  - Occasional nulls for `harbor_size` or `max_vessel_length`. We use `coalesce` to set default tiers.
  - Coordinate precision varies; safe to round to 4 decimal places.

## 3. Open-Meteo Marine Weather
- **Volume:** Hourly forecasts for 12 predefined chokepoint zones.
- **Quality Issues:** 
  - Occasional gaps in API response for future forecasts. Imputed using last-known-observation (ffill).
