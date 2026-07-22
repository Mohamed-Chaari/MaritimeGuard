{#
  Custom generic test: accepted_range

  Replaces dbt_utils.accepted_range so the project has NO external package
  dependency. Fewer moving parts, nothing to install, and it works offline —
  which matters for a demo that must not depend on the network being up.

  Usage in a schema.yml:

      columns:
        - name: order_quantity
          tests:
            - accepted_range:
                min_value: 1

        - name: event_hour
          tests:
            - accepted_range:
                min_value: 0
                max_value: 23

  The test passes when zero rows fall outside the range. NULLs are ignored so
  that range checking stays orthogonal to not_null, which is tested separately.
#}

{% test accepted_range(model, column_name, min_value=none, max_value=none) %}

select *
from {{ model }}
where {{ column_name }} is not null
  and (
    {% if min_value is not none %}
        {{ column_name }} < {{ min_value }}
        {% if max_value is not none %} or {% endif %}
    {% endif %}
    {% if max_value is not none %}
        {{ column_name }} > {{ max_value }}
    {% endif %}
  )

{% endtest %}
