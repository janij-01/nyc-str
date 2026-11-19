-- DBeaver: connect to the RDS endpoint (or localhost), port 5432, database nyc_str, SSL require.
-- Run one statement at a time. Raw tables are all text.

SELECT 'raw.listings' AS object_name, count(*) AS rows
FROM raw.listings
UNION ALL
SELECT 'raw.str_registrations', count(*)
FROM raw.str_registrations;

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'raw' AND table_name = 'listings'
ORDER BY ordinal_position;

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'raw' AND table_name = 'str_registrations'
ORDER BY ordinal_position;

SELECT *
FROM raw.str_registrations
ORDER BY source_row::integer
LIMIT 8;
