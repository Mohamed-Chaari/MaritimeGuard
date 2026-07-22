# Source Study: Maritime Intelligence

## Understanding AIS (Automatic Identification System)
AIS is an automated tracking system used on ships and by vessel traffic services (VTS).
- **Class A:** Required for all commercial vessels over 300 gross tonnage. High transmission rate.
- **Class B:** Used by smaller vessels. Slower transmission rate.

### Key Data Elements:
- **MMSI:** 9-digit unique identifier.
- **IMO:** 7-digit permanent identifier (does not change if the ship changes flag, unlike MMSI).
- **Navigation Status:** Underway using engine, at anchor, moored, restricted maneuverability, etc.

## Anomalies & Security Risks
Vessels occasionally "go dark" by turning off their AIS transponders. While this is legitimate in piracy-prone zones, in standard maritime corridors it is a strong indicator of:
- Illicit ship-to-ship transfers (smuggling, sanctions evasion).
- Illegal, Unreported, and Unregulated (IUU) fishing.

Our `fct_ais_anomalies` table calculates time gaps and distance gaps. If a vessel travels a distance physically impossible in the time elapsed (using Haversine distance), we flag a `blackout_with_movement` anomaly.

## References
1. [MarineCadastre AIS Guide](https://marinecadastre.gov/ais/)
2. [Open-Meteo Marine API](https://open-meteo.com/en/docs/marine-weather-api)
3. [NGA World Port Index](https://msi.nga.mil/Publications/WPI)
