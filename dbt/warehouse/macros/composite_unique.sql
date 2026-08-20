{#
  Generic model test: the given column combination must be unique.

  dbt ships `unique` for a single column only, and this project deliberately
  carries no package dependencies (no dbt_utils), so the composite form lives
  here. Returns the duplicated key tuples, so zero rows means PASS.

  Usage:
    data_tests:
      - composite_unique:
          columns: [sales_date, customer_state]
#}
{% test composite_unique(model, columns) %}
  select
    {{ columns | join(', ') }},
    count(*) as duplicate_rows
  from {{ model }}
  group by {{ columns | join(', ') }}
  having count(*) > 1
{% endtest %}
