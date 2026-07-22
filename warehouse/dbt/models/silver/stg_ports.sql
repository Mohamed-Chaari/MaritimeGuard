-- Staging: clean and standardize NGA World Port Index data.
select
    cast(port_index as integer)             as port_key,
    port_name,
    country,
    cast(latitude as double)                as latitude,
    cast(longitude as double)               as longitude,
    coalesce(harbor_size, 'Unknown')        as harbor_size,
    coalesce(harbor_type, 'Unknown')        as harbor_type,
    coalesce(shelter_quality, 'Unknown')    as shelter_quality,
    cast(channel_depth_m as double)         as channel_depth_m,
    cast(anchorage_depth_m as double)       as anchorage_depth_m,
    cast(cargo_pier_depth_m as double)      as cargo_pier_depth_m,
    coalesce(has_dry_dock, 'No')            as has_dry_dock,
    coalesce(has_railway, 'No')             as has_railway,
    coalesce(has_provisions, 'No')          as has_provisions,
    coalesce(has_fuel_oil, 'No')            as has_fuel_oil,
    cast(max_vessel_length_m as integer)    as max_vessel_length_m,
    cast(tide_range_m as double)            as tide_range_m
from {{ source('raw', 'raw_ports') }}
where port_name is not null
