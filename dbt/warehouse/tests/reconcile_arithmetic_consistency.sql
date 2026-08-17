-- Property test: diff_amount must always be exactly the difference of the two
-- sides it reports. This is independent of whether the data reconciles -
-- mart_reconciliation.sql asserts that. This one asserts the view cannot lie
-- about its own arithmetic, which would make every reconciliation verdict
-- meaningless.
--
-- Holds on any data, including source-only and mart-only days, because both
-- sides are COALESCEd to 0 before subtraction.

select
  sales_date,
  mart_gross_sales,
  source_gross_sales,
  diff_amount,
  round(mart_gross_sales - source_gross_sales - diff_amount, 2) as arithmetic_error
from {{ ref('v_reconcile_sales_daily') }}
where round(mart_gross_sales - source_gross_sales - diff_amount, 2) <> 0
