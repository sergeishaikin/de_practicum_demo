{#
  Generic column test: the column must never hold a negative value.

  Applied to money and count columns where the business forbids negatives
  (Olist has no refunds or reversals in this dataset). Returns violating rows,
  so zero rows means PASS.
#}
{% test non_negative(model, column_name) %}
  select {{ column_name }}
  from {{ model }}
  where {{ column_name }} < 0
{% endtest %}
