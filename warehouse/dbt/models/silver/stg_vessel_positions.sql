-- Staging: clean and standardize AIS vessel positions.
-- Deduplicates on (MMSI, BaseDateTime), filters invalid coordinates,
-- casts all columns to proper types, and renames to snake_case.
select
    MMSI                                as mmsi,
    cast(BaseDateTime as timestamp)     as position_ts,
    cast(LAT as double)                 as latitude,
    cast(LON as double)                 as longitude,
    cast(SOG as double)                 as sog,
    cast(COG as double)                 as cog,
    coalesce(cast(Heading as double), cast(COG as double)) as heading,
    nullif(trim(VesselName), '')        as vessel_name,
    nullif(trim(IMO), '')               as imo,
    nullif(trim(CallSign), '')          as call_sign,
    cast(VesselType as integer)         as vessel_type_code,
    cast(Status as integer)             as nav_status,
    cast(Length as double)              as length_m,
    cast(Width as double)               as width_m,
    cast(Draft as double)               as draft_m,
    nullif(trim(Cargo), '')             as cargo_code,
    nullif(trim(TransceiverClass), '')  as transceiver_class,
    -- row-number dedup: keep the latest ping for each (mmsi, timestamp) pair
    row_number() over (
        partition by MMSI, cast(BaseDateTime as timestamp)
        order by coalesce(cast(Length as double), 0) desc  -- prefer the richer record
    ) as _rn
from {{ source('raw', 'raw_vessel_positions') }}
where cast(LAT as double) between -90 and 90
  and cast(LON as double) between -180 and 180
  and cast(LAT as double) != 0          -- (0,0) is the "null island" AIS default
  and cast(LON as double) != 0
  and cast(BaseDateTime as timestamp) is not null
qualify _rn = 1
