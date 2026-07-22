-- One Big Table: fully denormalized vessel tracking for fast BI on DuckDB.
-- Joins the position fact with all dimensions so BI tools need no runtime joins.
select
    f.vessel_key,
    f.position_ts,
    f.latitude,
    f.longitude,
    f.sog,
    f.cog,
    f.heading,
    f.nav_status,
    f.distance_nm,
    f.time_gap_minutes,
    -- vessel dimension
    dv.vessel_name,
    dv.imo,
    dv.vessel_type_desc,
    dv.length_m,
    dv.width_m,
    dv.draft_m,
    dv.call_sign,
    -- time dimension
    dt.date_key,
    dt.hour,
    dt.day_of_week,
    dt.month,
    dt.quarter,
    dt.year,
    dt.season,
    dt.is_peak_trade_season,
    dt.watch_period
from {{ ref('fct_vessel_positions') }} f
left join {{ ref('dim_vessels') }} dv on f.vessel_key = dv.vessel_key
left join {{ ref('dim_time') }}    dt on f.time_key   = dt.time_key
