-- Weather zone dimension: maritime chokepoints and shipping regions.
-- Static reference — defines the zones used by stg_marine_weather.
select * from (
    values
        (1,  'strait_of_gibraltar',   'Strait of Gibraltar',    35.96,  -5.60,  30),
        (2,  'english_channel',       'English Channel',        50.50,  -1.00,  40),
        (3,  'suez_canal_north',      'Suez Canal (North)',     31.27,  32.31,  20),
        (4,  'strait_of_hormuz',      'Strait of Hormuz',       26.60,  56.25,  25),
        (5,  'malacca_strait',        'Malacca Strait',          2.50, 101.50,  30),
        (6,  'cape_good_hope',        'Cape of Good Hope',     -34.35,  18.50,  50),
        (7,  'panama_canal_atlantic', 'Panama Canal (Atlantic)', 9.38, -79.92,  15),
        (8,  'gulf_of_mexico_central','Gulf of Mexico (Central)',27.00, -90.00,  80),
        (9,  'houston_ship_channel',  'Houston Ship Channel',   29.50, -94.80,  20),
        (10, 'new_orleans_approach',  'New Orleans Approach',   29.00, -89.50,  25),
        (11, 'tampa_bay_approach',    'Tampa Bay Approach',     27.60, -82.80,  20),
        (12, 'corpus_christi_approach','Corpus Christi Approach',27.70, -97.10,  20)
) as t(zone_key, zone_code, zone_name, center_lat, center_lon, radius_nm)
