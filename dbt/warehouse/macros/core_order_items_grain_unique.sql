{% test core_order_items_grain_unique(model) %}
  select order_id, order_item_id
  from {{ model }}
  group by order_id, order_item_id
  having count(*) > 1
{% endtest %}
