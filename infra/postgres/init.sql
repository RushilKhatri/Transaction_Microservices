-- infra/postgres/init.sql
-- Both POSTGRES_DB and POSTGRES_USER are handled automatically by the
-- official postgres image via environment variables.
-- This file intentionally left with only GRANT to ensure the user
-- has full privileges on the database.

\connect banking;
GRANT ALL PRIVILEGES ON DATABASE banking TO banking_user;
GRANT ALL ON SCHEMA public TO banking_user;
