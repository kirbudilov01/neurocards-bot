/* Init Metabase database on first container start */
-- Creates a separate database for Metabase owned by 'neurocards' user
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_database WHERE datname = 'metabase'
    ) THEN
        PERFORM dblink_connect('conn', 'dbname=' || current_database());
        EXECUTE 'CREATE DATABASE metabase';
        -- Ownership will default to current user; ensure neurocards owns it if exists
    END IF;
EXCEPTION WHEN others THEN
    -- Fallback: try plain create (will fail if exists)
    BEGIN
        EXECUTE 'CREATE DATABASE metabase';
    EXCEPTION WHEN duplicate_database THEN
        NULL;
    END;
END $$;
