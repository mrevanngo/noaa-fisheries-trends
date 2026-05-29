"""
load_to_postgres.py
===================
Loads data/landings_raw.csv into PostgreSQL and runs the SQL setup
(schema + clean). After this, the analytical SQL in /sql and the
Streamlit dashboard are ready to use.

Usage:
    export PGHOST=localhost PGDATABASE=fisheries PGUSER=postgres PGPASSWORD=...
    python scripts/load_to_postgres.py

Uses COPY for a fast bulk load rather than row-by-row INSERTs — the right
tool when loading a whole CSV.
"""

import os
import psycopg2


def conn():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "fisheries"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", ""),
    )


def run_sql_file(cur, path):
    with open(path) as f:
        cur.execute(f.read())
    print(f"  ran {path}")


def main():
    c = conn()
    c.autocommit = True
    cur = c.cursor()

    print("Creating schema...")
    run_sql_file(cur, "sql/01_schema.sql")

    print("Bulk-loading CSV via COPY...")
    with open("data/landings_raw.csv") as f:
        cur.copy_expert(
            "COPY landings_raw (tsn, ts_afs_name, ts_scientific_name, region_name, "
            "state_name, year, pounds, dollars, tot_count, source, collection) "
            "FROM STDIN WITH CSV HEADER",
            f,
        )

    print("Cleaning into analysis table...")
    run_sql_file(cur, "sql/02_clean.sql")

    cur.execute("SELECT COUNT(*) FROM landings;")
    print(f"Done. landings rows: {cur.fetchone()[0]:,}")
    cur.close()
    c.close()


if __name__ == "__main__":
    main()
