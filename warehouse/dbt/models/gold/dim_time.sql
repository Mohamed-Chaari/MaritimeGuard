-- Time dimension with hourly grain for maritime operations.
-- Covers 2024-01-01 to 2025-12-31 (2 years, 17,520 hours).
-- Includes maritime-specific attributes: trade season, watch period.
select
    ts                                                  as time_key,
    cast(ts as date)                                    as date_key,
    extract(hour from ts)                               as hour,
    extract(dow from ts)                                as day_of_week,
    extract(day from ts)                                as day_of_month,
    extract(month from ts)                              as month,
    extract(quarter from ts)                            as quarter,
    extract(year from ts)                               as year,
    case when extract(dow from ts) in (0, 6) then 1 else 0 end as is_weekend,
    -- maritime seasons
    case extract(month from ts)
        when 12 then 'Winter'  when 1 then 'Winter'  when 2 then 'Winter'
        when 3  then 'Spring'  when 4 then 'Spring'  when 5 then 'Spring'
        when 6  then 'Summer'  when 7 then 'Summer'  when 8 then 'Summer'
        when 9  then 'Autumn'  when 10 then 'Autumn' when 11 then 'Autumn'
    end as season,
    -- peak trade season: Q4 (pre-holiday shipping rush) and Q1 (post-holiday)
    case when extract(month from ts) in (9, 10, 11, 12, 1, 2) then 1 else 0 end
        as is_peak_trade_season,
    -- maritime watch periods (4-hour watches)
    case
        when extract(hour from ts) between 0  and 3  then 'Middle Watch'
        when extract(hour from ts) between 4  and 7  then 'Morning Watch'
        when extract(hour from ts) between 8  and 11 then 'Forenoon Watch'
        when extract(hour from ts) between 12 and 15 then 'Afternoon Watch'
        when extract(hour from ts) between 16 and 19 then 'First Dog/Second Dog'
        else 'First Watch'
    end as watch_period
from (
    select cast('2024-01-01' as timestamp)
           + interval (n) hour as ts
    from range(0, 17520) t(n)
)
