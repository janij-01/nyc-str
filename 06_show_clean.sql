-- Run after 05_clean.py. First statement is the side-by-side shot.

SELECT
    r.id,
    r.price AS price_raw,
    c.price AS price_clean,
    r.minimum_nights AS nights_raw,
    c.minimum_nights AS nights_clean,
    r.license AS license_raw,
    c.license_missing
FROM raw.listings AS r
JOIN clean.listings AS c ON c.id = r.id
WHERE r.price LIKE '%,%' AND r.license IS NULL
ORDER BY r.id
LIMIT 1;

SELECT 'raw.listings' AS object_name, count(*) AS rows FROM raw.listings
UNION ALL SELECT 'clean.listings', count(*) FROM clean.listings
UNION ALL SELECT 'raw.str_registrations', count(*) FROM raw.str_registrations
UNION ALL SELECT 'clean.str_registrations', count(*) FROM clean.str_registrations
UNION ALL SELECT 'clean.registration_listings', count(*) FROM clean.registration_listings;

SELECT
    registration_number,
    strr_status,
    is_valid,
    borough,
    zip
FROM clean.str_registrations
ORDER BY registration_number
LIMIT 8;
