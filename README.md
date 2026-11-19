# NYC short-term rental ingestion

C2 Group 8, 95-815. These scripts load the three raw files and write the cleaned tables. The CSV, Excel, and JSON files stay on disk and are not in this repo.

PostgreSQL and MongoDB run locally. Connection strings are at the top of `01_import.py` and `05_clean.py` (localhost, database `nyc_str`).

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
