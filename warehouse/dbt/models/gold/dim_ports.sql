-- Port dimension from the cleaned NGA World Port Index.
-- Adds a harbor_size_rank for sorting and a capacity_tier classification.
select
    port_key,
    port_name,
    country,
    latitude,
    longitude,
    harbor_size,
    harbor_type,
    shelter_quality,
    channel_depth_m,
    anchorage_depth_m,
    cargo_pier_depth_m,
    has_dry_dock,
    has_railway,
    has_provisions,
    has_fuel_oil,
    max_vessel_length_m,
    tide_range_m,
    -- rank for ordering/filtering
    case harbor_size
        when 'Large'      then 1
        when 'Medium'     then 2
        when 'Small'      then 3
        when 'Very Small' then 4
        else 5
    end as harbor_size_rank,
    -- capacity tier for OLAP drill-down
    case
        when harbor_size = 'Large' and channel_depth_m >= 14 then 'Tier 1 - Deep Water'
        when harbor_size in ('Large', 'Medium')              then 'Tier 2 - Major'
        when harbor_size = 'Small'                           then 'Tier 3 - Regional'
        else 'Tier 4 - Minor'
    end as capacity_tier
from {{ ref('stg_ports') }}
