#!/usr/bin/env python3
"""Initial cleaning. Reads the raw databases and writes new tables.

Raw files and raw.listings / raw.str_registrations / complaints_311_raw
are not updated. Edit the rules below, then run this file again.
"""

import csv
from pathlib import Path

import psycopg2
from pymongo import MongoClient

PG_DSN = "host=localhost port=5432 dbname=nyc_str user=postgres password=postgres"
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "nyc_str"

# Only this status counts as a valid registration. Other statuses are kept.
VALID_STATUS = "Registered"

# Rows that are not this complaint are left out of the clean collection.
KEEP_COMPLAINT_TYPE = "Special Projects Inspection Team (SPIT)"
KEEP_DESCRIPTOR = "Illegal Hotel Rooms In Residential Building"

HERE = Path(__file__).resolve().parent
LOG_PATH = HERE / "cleaning_log.csv"


def main():
    pg = psycopg2.connect(PG_DSN)
    pg.autocommit = False
    mongo = MongoClient(MONGO_URI)
    log = []
    try:
        with pg.cursor() as cur:
            clean_listings(cur, log)
            clean_registrations(cur, log)
        pg.commit()
        clean_complaints(mongo, log)
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()
        mongo.close()

    write_log(log)
    print("\n另存为新表")
    for step, detail, count in log:
        if step.endswith("_written"):
            print(f"  {detail:<42} {count}")
    print(f"\ncleaning_log.csv 已写入 {LOG_PATH}")


def clean_listings(cur, log):
    print("① 房源")
    cur.execute(
        """
        SELECT
            count(*) AS rows,
            count(DISTINCT id) AS ids,
            count(*) FILTER (WHERE price IS NULL) AS price_blank,
            count(*) FILTER (WHERE price LIKE '%,%') AS price_comma,
            count(*) FILTER (WHERE minimum_nights IS NULL) AS nights_blank,
            count(*) FILTER (WHERE license IS NULL) AS license_blank
        FROM raw.listings
        """
    )
    rows, ids, price_blank, price_comma, nights_blank, license_blank = cur.fetchone()
    print(f"⚠ {rows} 行，不同的 id 有 {ids} 个")
    print(f"⚠ price：{price_blank} 行为空，{price_comma} 行带逗号，其余非空价格带 $")
    print(f"⚠ minimum_nights：{nights_blank} 行为空")
    print(f"⚠ license：{license_blank} 行为空。这些行保留，并标记 license_missing")
    log += [
        ("listings_price_blank", "raw.listings price is null", price_blank),
        ("listings_nights_blank", "raw.listings minimum_nights is null", nights_blank),
        ("listings_license_blank", "raw.listings license is null", license_blank),
    ]

    print("✓ price 去掉 $ 和逗号，转成 numeric。空的仍是空")
    print("✓ minimum_nights 转成 integer。空的仍是空")
    print("✓ 增加 license_missing。空 license 不删除")
    cur.execute("CREATE SCHEMA IF NOT EXISTS clean")
    cur.execute("DROP TABLE IF EXISTS clean.listings")
    cur.execute(
        """
        CREATE TABLE clean.listings AS
        SELECT
            id,
            host_id,
            neighbourhood_cleansed,
            neighbourhood_group_cleansed,
            room_type,
            latitude::numeric AS latitude,
            longitude::numeric AS longitude,
            price AS price_raw,
            CASE
                WHEN price IS NULL THEN NULL
                ELSE replace(replace(price, '$', ''), ',', '')::numeric
            END AS price,
            minimum_nights AS minimum_nights_raw,
            CASE
                WHEN minimum_nights IS NULL THEN NULL
                ELSE minimum_nights::integer
            END AS minimum_nights,
            license,
            (license IS NULL) AS license_missing
        FROM raw.listings
        """
    )
    cur.execute("SELECT count(*) FROM clean.listings")
    written = cur.fetchone()[0]
    log.append(("listings_written", "PostgreSQL clean.listings", written))

    cur.execute(
        """
        SELECT id, price_raw, price, minimum_nights_raw, minimum_nights,
               license, license_missing
        FROM clean.listings
        WHERE price_raw LIKE '%,%' AND license IS NULL
        ORDER BY id
        LIMIT 1
        """
    )
    sample = cur.fetchone()
    print("\n同一条记录：清洗前 vs 清洗后")
    print(f"  id                  {sample[0]}")
    print(f"  price               {sample[1]}  ->  {sample[2]}")
    print(f"  minimum_nights      {sample[3]}  ->  {sample[4]}")
    license_text = sample[5] if sample[5] else "(空)"
    print(f"  license             {license_text}  ->  {license_text}, license_missing={sample[6]}")
    print()


def clean_registrations(cur, log):
    print("② 登记表")
    cur.execute(
        """
        SELECT
            count(*) AS rows,
            count(*) FILTER (WHERE registration_number IS NULL) AS continuations
        FROM raw.str_registrations
        """
    )
    rows, continuations = cur.fetchone()
    print(f"⚠ {rows} 行里有 {continuations} 行续行：登记号为空，只填了平台和链接")
    print("✓ 续行补上上一行的登记号")
    print("✓ 拆成 clean.str_registrations（一个登记号一行）和 clean.registration_listings（一个链接一行）")
    print(f"✓ 状态是 {VALID_STATUS} 的标成 is_valid。其他状态保留，is_valid 为 false")

    cur.execute("DROP TABLE IF EXISTS clean.str_registrations")
    cur.execute(
        """
        CREATE TABLE clean.str_registrations AS
        SELECT
            registration_number,
            strr_status,
            (strr_status = %s) AS is_valid,
            registration_expiration_date,
            street_address,
            unit_number,
            borough,
            zip,
            bin
        FROM raw.str_registrations
        WHERE registration_number IS NOT NULL
        """,
        (VALID_STATUS,),
    )
    cur.execute("DROP TABLE IF EXISTS clean.registration_listings")
    cur.execute(
        """
        CREATE TABLE clean.registration_listings AS
        WITH ordered AS (
            SELECT
                source_row,
                registration_number,
                booking_service,
                listing_url_or_listing_number,
                count(registration_number) OVER (ORDER BY source_row::integer) AS grp
            FROM raw.str_registrations
        ),
        filled AS (
            SELECT
                source_row,
                first_value(registration_number) OVER (
                    PARTITION BY grp ORDER BY source_row::integer
                ) AS registration_number,
                booking_service,
                listing_url_or_listing_number
            FROM ordered
        )
        SELECT
            registration_number,
            booking_service,
            listing_url_or_listing_number AS listing_url
        FROM filled
        WHERE listing_url_or_listing_number IS NOT NULL
        ORDER BY source_row::integer
        """
    )
    cur.execute("SELECT count(*) FROM clean.str_registrations")
    registration_count = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM clean.str_registrations WHERE is_valid")
    valid_count = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM clean.registration_listings")
    link_count = cur.fetchone()[0]
    log += [
        ("registrations_continuation", "raw continuation rows", continuations),
        ("registrations_written", "PostgreSQL clean.str_registrations", registration_count),
        ("registrations_valid", f"status = {VALID_STATUS}", valid_count),
        ("registration_listings_written", "PostgreSQL clean.registration_listings", link_count),
    ]

    cur.execute(
        """
        WITH ordered AS (
            SELECT
                source_row,
                registration_number,
                booking_service,
                listing_url_or_listing_number,
                count(registration_number) OVER (ORDER BY source_row::integer) AS grp
            FROM raw.str_registrations
        ),
        filled AS (
            SELECT
                registration_number AS before_number,
                first_value(registration_number) OVER (
                    PARTITION BY grp ORDER BY source_row::integer
                ) AS after_number,
                listing_url_or_listing_number AS listing_url
            FROM ordered
        )
        SELECT after_number, listing_url
        FROM filled
        WHERE before_number IS NULL
        LIMIT 1
        """
    )
    after, listing_url = cur.fetchone()
    print("\n同一条记录：清洗前 vs 清洗后")
    print(f"  registration_number  (空)  ->  {after}")
    print(f"  listing_url          {listing_url}")
    print(f"  登记表 {registration_count} 行，其中有效 {valid_count} 行")
    print(f"  房源链接 {link_count} 行")
    print()


def clean_complaints(mongo, log):
    print("③ 311")
    source = mongo[MONGO_DB]["complaints_311_raw"]
    target = mongo[MONGO_DB]["complaints_311_clean"]
    target.drop()

    kept = []
    dropped = 0
    missing_coords = 0
    sample = None
    for document in source.find():
        if (
            document.get("complaint_type") != KEEP_COMPLAINT_TYPE
            or document.get("descriptor") != KEEP_DESCRIPTOR
        ):
            dropped += 1
            continue
        coordinates = (document.get("location") or {}).get("coordinates")
        longitude = latitude = None
        coords_missing = True
        if (
            isinstance(coordinates, list)
            and len(coordinates) == 2
            and coordinates[0] is not None
            and coordinates[1] is not None
        ):
            longitude = float(coordinates[0])
            latitude = float(coordinates[1])
            coords_missing = False
        else:
            missing_coords += 1
        cleaned = {
            "unique_key": document.get("unique_key"),
            "created_date": document.get("created_date"),
            "complaint_type": document.get("complaint_type"),
            "descriptor": document.get("descriptor"),
            "borough": document.get("borough"),
            "incident_zip": document.get("incident_zip"),
            "longitude": longitude,
            "latitude": latitude,
            "coords_missing": coords_missing,
            "location": document.get("location"),
        }
        kept.append(cleaned)
        if sample is None and not coords_missing:
            sample = (coordinates, longitude, latitude, document.get("unique_key"))

    if kept:
        target.insert_many(kept)
    written = target.count_documents({})
    print(f"⚠ 原始 {source.count_documents({})} 条，其中 {dropped} 条不是非法短租投诉")
    print(f"⚠ {missing_coords} 条缺坐标。这些条保留，并标记 coords_missing")
    print("✓ 从 location.coordinates 取出经度、纬度")
    print(f"✓ 只保留 {KEEP_DESCRIPTOR}")
    print("\n同一条记录：清洗前 vs 清洗后")
    print(f"  unique_key   {sample[3]}")
    print(f"  location     {sample[0]}")
    print(f"  longitude    {sample[1]}")
    print(f"  latitude     {sample[2]}")
    print(f"  清洗后 {written} 条")
    print()
    log += [
        ("complaints_dropped", "non-matching complaints left out", dropped),
        ("complaints_coords_missing", "coords_missing = true", missing_coords),
        ("complaints_written", "MongoDB nyc_str.complaints_311_clean", written),
    ]


def write_log(log):
    with LOG_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["step", "detail", "row_count"])
        writer.writerows(log)


if __name__ == "__main__":
    main()
