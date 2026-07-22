{% snapshot dim_vessels_scd2 %}
{{
  config(
    target_schema='gold',
    unique_key='mmsi',
    strategy='check',
    check_cols=['vessel_name', 'vessel_type_code'],
    invalidate_hard_deletes=True
  )
}}
-- SCD Type 2: dbt maintains dbt_valid_from / dbt_valid_to / dbt_scd_id automatically.
-- When a vessel's name or type changes (e.g., re-flagging, name change after sale),
-- a new versioned row is written and the old one is closed off.
-- This is a genuine maritime event: flag changes indicate regulatory jurisdiction changes.
select
    mmsi,
    any_value(IMO)               as imo,
    any_value(VesselName)        as vessel_name,
    any_value(VesselType)        as vessel_type_code,
    any_value(CallSign)          as call_sign,
    round(any_value(Length), 1)  as length_m,
    round(any_value(Width), 1)   as width_m,
    round(any_value(Draft), 1)   as draft_m
from {{ source('raw', 'raw_vessel_positions') }}
where MMSI is not null
  and cast(LAT as double) between -90 and 90
  and cast(LON as double) between -180 and 180
group by mmsi
{% endsnapshot %}
