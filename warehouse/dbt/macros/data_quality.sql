{#
  Data-quality scoring — implements the course "étude des données" grille.

  For each source the course asks for two 0–3 ratings:
    qualité :  0 inexploitable · 1 peu exploitable · 2 exploitable après traitement · 3 exploitable sans traitement
    utilité :  0 sans intérêt · 1 doc seulement · 2 utile a priori · 3 utile avec certitude

  This macro derives an automatic *qualité* score from measurable signals
  (null rate, duplicate rate) so the study is reproducible, not just manual.
  The *utilité* score stays a business judgment recorded in the source's
  schema.yml meta block.
#}

{% macro quality_score(relation, key_column, columns) %}
    with checks as (
        select
            count(*) as total_rows,
            count(distinct {{ key_column }}) as distinct_keys,
            {% for col in columns -%}
            sum(case when {{ col }} is null then 1 else 0 end) as null_{{ col }}{{ "," if not loop.last }}
            {% endfor %}
        from {{ relation }}
    ),
    scored as (
        select
            total_rows,
            (total_rows - distinct_keys) as duplicate_rows,
            (
                {% for col in columns -%}
                null_{{ col }}{{ " + " if not loop.last }}
                {% endfor %}
            ) as total_nulls
        from checks
    )
    select
        total_rows,
        duplicate_rows,
        total_nulls,
        round(100.0 * total_nulls / nullif(total_rows * {{ columns | length }}, 0), 2) as null_pct,
        case
            when total_rows = 0 then 0                              -- 0 : inexploitable
            when duplicate_rows > 0
                 or total_nulls > total_rows then 1                 -- 1 : peu exploitable
            when total_nulls > 0 then 2                             -- 2 : exploitable après traitement
            else 3                                                  -- 3 : exploitable sans traitement
        end as qualite_auto
    from scored
{% endmacro %}
