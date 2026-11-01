"""Copy the Parquet tables from statcage.ingest.build into Postgres.

Every run replaces all rows inside one transaction: if anything fails,
Postgres undoes the whole load and the old data stays.
"""

import pandas as pd

from statcage.db import connect
from statcage.ingest.build import PROCESSED_DIR

# Parents before children, so every foreign key already has its target row.
TABLES = ["events", "fighters", "fights", "fight_stats"]


def rows_for_copy(table: pd.DataFrame):
    """Yield each row as plain Python values, with every kind of missing value as None (NULL)."""
    for row in table.to_dict("records"):
        yield [None if pd.isna(value) else value for value in row.values()]


def load_all() -> None:
    tables = {name: pd.read_parquet(PROCESSED_DIR / f"{name}.parquet") for name in TABLES}

    with connect() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE " + ", ".join(TABLES))
        for name, table in tables.items():
            columns = ", ".join(table.columns)
            with cur.copy(f"COPY {name} ({columns}) FROM STDIN") as copy:
                for row in rows_for_copy(table):
                    copy.write_row(row)

            cur.execute(f"SELECT count(*) FROM {name}")
            count = cur.fetchone()[0]
            if count != len(table):
                raise ValueError(f"{name}: loaded {count} rows, expected {len(table)}")
            print(f"{name}: {count:,} rows loaded")
    # Leaving the "with connect()" block commits; an error inside it rolls everything back.


if __name__ == "__main__":
    load_all()
