select 'create database e2e'
where not exists (select from pg_database where datname = 'e2e')\gexec
