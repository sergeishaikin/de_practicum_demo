create schema if not exists stg;
create schema if not exists core;
create schema if not exists marts;
-- Bootstrap owns the namespace; dbt owns every relation inside it. The schema is
-- created here so that reader provisioning can grant on it before dbt has ever
-- run. See docs/warehouse/W1-dbt-ownership.md.
create schema if not exists staging;
