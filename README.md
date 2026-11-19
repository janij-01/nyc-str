# NYC short-term rental ingestion

C2 Group 8, 95-815. These scripts load the three raw files and write the cleaned tables. The CSV, Excel, and JSON files stay in the team's shared folder and are not in this repo.

## Where the data lives

- PostgreSQL on Amazon RDS (instance `de-postgres`, us-east-2), database `nyc_str`: schemas `raw` and `clean`.
- MongoDB Atlas, database `nyc_str`: collections `complaints_311_raw` and `complaints_311_clean`.

Ask the project manager for the endpoints and credentials. Your IP must be added to the RDS security group (port 5432) and to Atlas Network Access.

## Setup

```bash
pip install psycopg2-binary pymongo openpyxl
export PG_DSN="host=<rds-endpoint> port=5432 dbname=nyc_str user=<user> password=<password> sslmode=require"
export MONGO_URI="mongodb+srv://<user>:<password>@<atlas-cluster>/"
```

Both scripts read `PG_DSN` and `MONGO_URI` from the environment. If they are not set, the scripts fall back to a local PostgreSQL and MongoDB on `localhost`. Never commit credentials.

## Run

```bash
cd nyc-str
DATA_DIR=/path/to/data
python3 01_import.py \
  --listings "$DATA_DIR/listings.csv.gz" \
  --registrations "$DATA_DIR/ose-str-registration-dataset-2026-11-02.xlsx" \
  --complaints "$DATA_DIR/erm2-nwe9.json"
python3 05_clean.py
```

`04_show_storage.sql` and `06_show_clean.sql` are the DBeaver queries. `cleaning_log.csv` is the row count written by `05_clean.py`.
