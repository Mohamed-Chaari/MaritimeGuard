-- Staging: derive port call events from AIS position data.
-- A "port call" is detected when a vessel's speed drops below 1 knot
-- within proximity of a known port (< 0.1 degrees ≈ 6 nm).
-- The arrival is the first slow-speed ping; the departure is the next
-- high-speed ping after the stay. Duration is calculated in hours.
with vessel_near_port as (
    select
        v.mmsi,
        v.position_ts,
        v.latitude,
        v.longitude,
        v.sog,
        p.port_index                                       as port_id,
        p.port_name,
        -- simple proximity check: within ~0.1 degrees (~6 nm) of port
        sqrt(power(v.latitude - p.latitude, 2)
           + power(v.longitude - p.longitude, 2))          as dist_deg
    from {{ ref('stg_vessel_positions') }} v
    cross join {{ source('raw', 'raw_ports') }} p
    where sqrt(power(v.latitude - p.latitude, 2)
             + power(v.longitude - p.longitude, 2)) < 0.1
),
port_events as (
    select
        mmsi,
        port_id,
        port_name,
        position_ts,
        sog,
        latitude,
        longitude,
        -- detect transitions: moving->stopped = arrival, stopped->moving = departure
        case when sog < 1.0 and lag(sog, 1, 999) over w >= 1.0 then 'arrival'
             when sog >= 1.0 and lag(sog, 1, 0) over w < 1.0 then 'departure'
        end as event_type
    from vessel_near_port
    window w as (partition by mmsi, port_id order by position_ts)
),
arrivals as (
    select
        mmsi,
        port_id,
        port_name,
        position_ts as arrival_ts,
        latitude    as arrival_lat,
        longitude   as arrival_lon,
        lead(position_ts) over (partition by mmsi, port_id order by position_ts)
            as departure_ts
    from port_events
    where event_type = 'arrival'
)
select
    mmsi,
    port_id,
    port_name,
    arrival_ts,
    departure_ts,
    arrival_lat,
    arrival_lon,
    -- duration in hours (null if vessel hasn't departed yet)
    round(
        epoch(departure_ts - arrival_ts) / 3600.0, 2
    ) as duration_hours
from arrivals
where arrival_ts is not null
