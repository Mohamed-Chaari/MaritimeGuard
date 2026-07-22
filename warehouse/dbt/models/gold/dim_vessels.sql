-- Vessel dimension deduplicated ON THE BUSINESS KEY (mmsi).
-- SELECT DISTINCT over all columns is NOT sufficient: a vessel observed with
-- differing attributes would produce multiple rows per key and fan out the
-- fact join. Enforced by the unique test in _schema.yml.
-- Note: the SCD Type 2 version is maintained via dbt snapshot (snapshots/dim_vessels.sql).
-- This model is the Type 1 "current state" version for simple joins.
select
    mmsi                                            as vessel_key,
    any_value(imo)                                  as imo,
    any_value(vessel_name)                          as vessel_name,
    any_value(vessel_type_code)                     as vessel_type_code,
    -- decode AIS vessel type codes to human-readable descriptions
    case any_value(vessel_type_code)
        when 30 then 'Fishing'
        when 36 then 'Sailing'
        when 37 then 'Pleasure Craft'
        when 40 then 'High Speed Craft'
        when 52 then 'Tug'
        when 60 then 'Passenger'
        when 70 then 'Cargo'
        when 80 then 'Tanker'
        else 'Other (' || cast(any_value(vessel_type_code) as varchar) || ')'
    end                                             as vessel_type_desc,
    any_value(call_sign)                            as call_sign,
    round(any_value(length_m), 1)                   as length_m,
    round(any_value(width_m), 1)                    as width_m,
    round(any_value(draft_m), 1)                    as draft_m,
    any_value(cargo_code)                           as cargo_code,
    any_value(transceiver_class)                    as transceiver_class,
    count(*)                                        as total_pings,
    min(position_ts)                                as first_seen,
    max(position_ts)                                as last_seen
from {{ ref('stg_vessel_positions') }}
group by mmsi
