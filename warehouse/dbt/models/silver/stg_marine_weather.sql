-- Staging: clean and standardize marine weather data from Open-Meteo.
select
    zone_name,
    cast(latitude as double)              as latitude,
    cast(longitude as double)             as longitude,
    cast(timestamp_utc as timestamp)      as weather_ts,
    cast(wave_height_m as double)         as wave_height_m,
    cast(wave_direction_deg as double)    as wave_direction_deg,
    cast(wave_period_s as double)         as wave_period_s,
    cast(wind_wave_height_m as double)    as wind_wave_height_m,
    cast(swell_wave_height_m as double)   as swell_wave_height_m,
    cast(wind_speed_10m_kmh as double)    as wind_speed_kmh,
    cast(wind_direction_10m_deg as double) as wind_direction_deg_10m,
    cast(wind_gusts_10m_kmh as double)    as wind_gusts_kmh,
    -- convert wind speed to knots for maritime convention
    round(cast(wind_speed_10m_kmh as double) * 0.539957, 1) as wind_speed_kts,
    -- Beaufort scale approximation
    case
        when cast(wind_speed_10m_kmh as double) < 2   then 0   -- Calm
        when cast(wind_speed_10m_kmh as double) < 6   then 1   -- Light air
        when cast(wind_speed_10m_kmh as double) < 12  then 2   -- Light breeze
        when cast(wind_speed_10m_kmh as double) < 20  then 3   -- Gentle breeze
        when cast(wind_speed_10m_kmh as double) < 29  then 4   -- Moderate breeze
        when cast(wind_speed_10m_kmh as double) < 39  then 5   -- Fresh breeze
        when cast(wind_speed_10m_kmh as double) < 50  then 6   -- Strong breeze
        when cast(wind_speed_10m_kmh as double) < 62  then 7   -- Near gale
        when cast(wind_speed_10m_kmh as double) < 75  then 8   -- Gale
        when cast(wind_speed_10m_kmh as double) < 89  then 9   -- Strong gale
        when cast(wind_speed_10m_kmh as double) < 103 then 10  -- Storm
        when cast(wind_speed_10m_kmh as double) < 117 then 11  -- Violent storm
        else 12                                                 -- Hurricane force
    end as beaufort_scale
from {{ source('raw', 'raw_marine_weather') }}
where cast(timestamp_utc as timestamp) is not null
