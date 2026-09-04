\set ON_ERROR_STOP on
\set reader_user `printf '%s' "$METADATA_SOURCE_READER_USER"`
\set reader_password `printf '%s' "$METADATA_SOURCE_READER_PASSWORD"`
\set reader_database `printf '%s' "$METADATA_SOURCE_READER_DATABASE"`

SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT',
  :'reader_user', :'reader_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'reader_user')\gexec

SELECT format(
  'ALTER ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT',
  :'reader_user', :'reader_password'
)
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'reader_user')\gexec

GRANT CONNECT ON DATABASE :"reader_database" TO :"reader_user";
GRANT USAGE ON SCHEMA core, stg, staging, marts TO :"reader_user";
GRANT SELECT ON ALL TABLES IN SCHEMA core, stg, staging, marts TO :"reader_user";
GRANT SELECT ON ALL SEQUENCES IN SCHEMA core, stg, staging, marts TO :"reader_user";
ALTER DEFAULT PRIVILEGES FOR ROLE app IN SCHEMA core, stg, staging, marts
  GRANT SELECT ON TABLES TO :"reader_user";
ALTER DEFAULT PRIVILEGES FOR ROLE app IN SCHEMA core, stg, staging, marts
  GRANT SELECT ON SEQUENCES TO :"reader_user";
