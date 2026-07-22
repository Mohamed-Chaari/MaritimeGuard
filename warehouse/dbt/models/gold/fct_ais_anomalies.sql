-- Fact 3: AIS anomalies — suspicious signal blackouts and speed jumps.
-- Grain: one row per flagged anomaly event.
-- Detects: (1) AIS blackouts (time gap > 2 hours), (2) impossible speed jumps,
-- (3) sudden position teleports that suggest intentional transponder shutoff.
with gaps as (
    select
        vessel_key,
        position_ts                          as anomaly_ts,
        latitude,
        longitude,
        sog,
        cog,
        time_key,
        time_gap_minutes,
        distance_nm,
        vessel_type_code,
        -- the implied speed to cover the distance in the time gap
        case when time_gap_minutes > 0 then
            round(distance_nm / (time_gap_minutes / 60.0), 1)
        end as implied_speed_kts
    from {{ ref('fct_vessel_positions') }}
    where time_gap_minutes is not null
)
select
    vessel_key,
    anomaly_ts,
    latitude                                     as last_known_lat,
    longitude                                    as last_known_lon,
    sog                                          as last_known_sog,
    time_key,
    time_gap_minutes,
    distance_nm                                  as distance_gap_nm,
    implied_speed_kts,
    -- classify anomaly type
    case
        when time_gap_minutes > 120 and distance_nm > 50
            then 'blackout_with_movement'        -- transponder off, vessel moved
        when time_gap_minutes > 120 and distance_nm <= 50
            then 'blackout_stationary'           -- transponder off, vessel stayed
        when implied_speed_kts > 40
            then 'impossible_speed'              -- teleport / spoofing
        when time_gap_minutes > 360
            then 'extended_blackout'             -- >6h gap, any distance
    end as anomaly_type,
    -- risk score: higher = more suspicious (0-100)
    least(100, round(
        (least(time_gap_minutes, 1440) / 14.4)   -- time gap component (max 100)
        * 0.4
        + (least(distance_nm, 500) / 5.0)         -- distance component (max 100)
        * 0.3
        + (case when implied_speed_kts > 25 then 100
                when implied_speed_kts > 15 then 50
                else 0 end)                        -- speed anomaly component
        * 0.3
    )) as risk_score
from gaps
where time_gap_minutes > 120                      -- only flag gaps > 2 hours
   or implied_speed_kts > 40                      -- or impossible speeds
