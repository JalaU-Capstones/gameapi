#!/bin/bash
set -euo pipefail

: "${GAMEAPI_APP_PASSWORD:?GAMEAPI_APP_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  -v app_password="$GAMEAPI_APP_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE gameapi_app LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gameapi_app')
\gexec

ALTER ROLE gameapi_app NOINHERIT NOCREATEDB NOCREATEROLE NOSUPERUSER;

GRANT USAGE ON SCHEMA public TO gameapi_app;
REVOKE CREATE ON SCHEMA public FROM gameapi_app;

DO $$
DECLARE
  tbl text;
BEGIN
  FOREACH tbl IN ARRAY ARRAY['users', 'gameplays', 'refresh_tokens', 'logs'] LOOP
    IF EXISTS (
      SELECT 1
      FROM pg_tables
      WHERE schemaname = 'public' AND tablename = tbl
    ) THEN
      EXECUTE format(
        'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE %I.%I TO gameapi_app',
        'public',
        tbl
      );
    END IF;
  END LOOP;

  IF EXISTS (
    SELECT 1
    FROM pg_tables
    WHERE schemaname = 'public' AND tablename = 'alembic_version'
  ) THEN
    EXECUTE 'REVOKE ALL ON TABLE public.alembic_version FROM gameapi_app';
  END IF;
END $$;

ALTER DEFAULT PRIVILEGES FOR ROLE gameapi IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO gameapi_app;
SQL
