-- Fact 2: port call events with duration and delay metrics.
-- Grain: one row per port call (vessel arrival at a port).
-- Shares conformed dimensions with fct_vessel_positions => galaxy schema.
select
    pc.mmsi                                                as vessel_key,
    pc.port_id                                             as port_key,
    pc.arrival_ts,
    pc.departure_ts,
    pc.duration_hours,
    cast(date_trunc('hour', pc.arrival_ts) as timestamp)   as time_key,
    pc.arrival_lat,
    pc.arrival_lon,
    -- delay flag: port call lasting more than 48 hours is considered a delay
    case when pc.duration_hours > 48 then 1 else 0 end     as is_extended_stay,
    -- categorize stay duration
    case
        when pc.duration_hours is null then 'in_port'     -- still at port
        when pc.duration_hours < 6     then 'brief_stop'
        when pc.duration_hours < 24    then 'day_call'
        when pc.duration_hours < 72    then 'standard_call'
        else 'extended_stay'
    end as stay_category
from {{ ref('stg_port_calls') }} pc
