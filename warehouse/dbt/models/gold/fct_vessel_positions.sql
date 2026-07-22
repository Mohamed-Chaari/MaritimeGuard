-- Fact 1: vessel position snapshots with calculated distance traveled.
-- Grain: one row per (vessel_key, position_ts).
-- Uses Haversine formula to compute distance from previous ping in nautical miles.
with lagged as (
    select
        mmsi                                               as vessel_key,
        position_ts,
        latitude,
        longitude,
        sog,
        cog,
        heading,
        nav_status,
        vessel_type_code,
        lag(latitude) over w                               as prev_lat,
        lag(longitude) over w                              as prev_lon,
        lag(position_ts) over w                            as prev_ts,
        cast(date_trunc('hour', position_ts) as timestamp) as time_key
    from {{ ref('stg_vessel_positions') }}
    window w as (partition by mmsi order by position_ts)
)
select
    vessel_key,
    position_ts,
    latitude,
    longitude,
    sog,
    cog,
    heading,
    nav_status,
    vessel_type_code,
    time_key,
    -- Haversine distance in nautical miles
    case when prev_lat is not null then
        round(
            3440.065 * 2 * asin(sqrt(
                power(sin(radians(latitude - prev_lat) / 2), 2)
                + cos(radians(prev_lat)) * cos(radians(latitude))
                  * power(sin(radians(longitude - prev_lon) / 2), 2)
            )), 2
        )
    end as distance_nm,
    -- time gap from previous ping in minutes
    case when prev_ts is not null then
        round(epoch(position_ts - prev_ts) / 60.0, 1)
    end as time_gap_minutes
from lagged
