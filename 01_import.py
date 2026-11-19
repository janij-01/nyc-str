#!/usr/bin/env python3
"""Load the three raw files. This step does not clean anything."""

import argparse
import csv
import gzip
import json
import os
import re

import openpyxl
import psycopg2
from psycopg2.extras import execute_values
from pymongo import MongoClient

PG_DSN = os.environ.get(
    "PG_DSN",
    "host=localhost port=5432 dbname=nyc_str user=postgres password=postgres",
)
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")


def column_name(name):
    text = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip()).strip("_").lower()
    if not text:
        text = "col"
    if text[0].isdigit():
        text = "c_" + text
    return text[:63]


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def create_text_table(cur, table, columns):
    cur.execute(f"DROP TABLE IF EXISTS {table}")
    definition = ", ".join(f"{quote(column)} text" for column in columns)
    cur.execute(f"CREATE TABLE {table} ({definition})")


def insert_rows(cur, table, columns, rows):
    if not rows:
        return
    sql = (
        f"INSERT INTO {table} ({', '.join(quote(column) for column in columns)}) "
        "VALUES %s"
    )
    execute_values(cur, sql, rows, page_size=500)


def blank_to_null(value):
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def load_listings(cur, path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        columns = []
        used = {}
        for name in header:
            column = column_name(name)
            if column in used:
                used[column] += 1
                column = f"{column}_{used[column]}"[:63]
            else:
                used[column] = 0
            columns.append(column)
        create_text_table(cur, "raw.listings", columns)
        pending = []
        count = 0
        for row in reader:
            if len(row) < len(columns):
                row = row + [""] * (len(columns) - len(row))
            pending.append(tuple(blank_to_null(value) for value in row[: len(columns)]))
            count += 1
            if len(pending) == 500:
                insert_rows(cur, "raw.listings", columns, pending)
                pending = []
        insert_rows(cur, "raw.listings", columns, pending)
    return count


def load_registrations(cur, path):
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    next(rows)  # title row
    header = next(rows)
    columns = [column_name(name) for name in header if name is not None]
    # source_row = the row number in the Excel sheet. Continuation rows are
    # filled from the row above, so cleaning must sort by this, not by ctid.
    create_text_table(cur, "raw.str_registrations", ["source_row"] + columns)
    pending = []
    count = 0
    for sheet_row, row in enumerate(rows, start=3):
        values = tuple(
            blank_to_null(row[index] if index < len(row) else None)
            for index in range(len(columns))
        )
        if all(value is None for value in values):
            continue
        pending.append((str(sheet_row),) + values)
        count += 1
        if len(pending) == 500:
            insert_rows(cur, "raw.str_registrations", ["source_row"] + columns, pending)
            pending = []
    insert_rows(cur, "raw.str_registrations", ["source_row"] + columns, pending)
    workbook.close()
    return count


def load_complaints(path):
    client = MongoClient(MONGO_URI)
    collection = client["nyc_str"]["complaints_311_raw"]
    collection.drop()
    with open(path, encoding="utf-8") as handle:
        documents = json.load(handle)
    for document in documents:
        document.pop("_id", None)
    for start in range(0, len(documents), 1000):
        collection.insert_many(documents[start : start + 1000])
    return collection.count_documents({})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--listings", required=True)
    parser.add_argument("--registrations", required=True)
    parser.add_argument("--complaints", required=True)
    args = parser.parse_args()

    connection = psycopg2.connect(PG_DSN)
    connection.autocommit = False
    with connection.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
        listing_count = load_listings(cur, args.listings)
        registration_count = load_registrations(cur, args.registrations)
    connection.commit()
    connection.close()
    complaint_count = load_complaints(args.complaints)

    print(f"[PostgreSQL] raw.listings             <- {listing_count} rows")
    print(f"[PostgreSQL] raw.str_registrations    <- {registration_count} rows")
    print(f"[MongoDB]    nyc_str.complaints_311_raw <- {complaint_count} documents")


if __name__ == "__main__":
    main()
