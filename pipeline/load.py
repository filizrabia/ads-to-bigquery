"""Idempotent loaders.

Every load replaces exactly one (date, platform) slice inside a transaction, so
re-running a day (late conversions, API restatements, a failed job) never
creates duplicates and never touches other platforms.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import date

from .schema import BIGQUERY_SCHEMA, COLUMNS, AdRow


class SQLiteLoader:
    """Local stand-in for the warehouse, used for development and tests."""

    def __init__(self, path: str = "ads.db", table: str = "ads_daily"):
        self.conn = sqlite3.connect(path)
        self.table = table
        sqlite_type = {"NUMERIC": "REAL", "FLOAT64": "REAL", "INT64": "INTEGER"}
        cols = ", ".join(f"{c} {sqlite_type.get(t, 'TEXT')}" for c, t in BIGQUERY_SCHEMA)
        self.conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({cols})")

    def replace_slice(self, day: date, platform: str, rows: Sequence[AdRow]) -> int:
        placeholders = ", ".join("?" for _ in COLUMNS)
        with self.conn:  # one transaction: delete + insert succeed or fail together
            self.conn.execute(f"DELETE FROM {self.table} WHERE date = ? AND platform = ?", (day.isoformat(), platform))
            self.conn.executemany(
                f"INSERT INTO {self.table} ({', '.join(COLUMNS)}) VALUES ({placeholders})",
                [tuple(r.to_record()[c] for c in COLUMNS) for r in rows],
            )
        return len(rows)


class BigQueryLoader:
    """Loads into a date-partitioned, platform-clustered BigQuery table.

    Rows go to a staging table first, then a multi-statement transaction swaps
    the (date, platform) slice in the target table.
    """

    def __init__(self, project: str, dataset: str, table: str = "ads_daily", location: str = "EU", client=None):
        if client is None:
            from google.cloud import bigquery  # imported lazily so local runs don't need it

            client = bigquery.Client(project=project, location=location)
        self.client = client
        self.project, self.dataset, self.table = project, dataset, table
        self.target = f"{project}.{dataset}.{table}"
        self.staging = f"{project}.{dataset}._stg_{table}"

    def ensure_table(self) -> None:
        from google.cloud import bigquery

        schema = [bigquery.SchemaField(name, typ) for name, typ in BIGQUERY_SCHEMA]
        table = bigquery.Table(self.target, schema=schema)
        table.time_partitioning = bigquery.TimePartitioning(field="date")
        table.clustering_fields = ["platform", "campaign_id"]
        self.client.create_table(table, exists_ok=True)

    def replace_slice(self, day: date, platform: str, rows: Sequence[AdRow]) -> int:
        from google.cloud import bigquery

        job_config = bigquery.LoadJobConfig(
            schema=[bigquery.SchemaField(name, typ) for name, typ in BIGQUERY_SCHEMA],
            write_disposition="WRITE_TRUNCATE",
        )
        records = [r.to_record() for r in rows]
        self.client.load_table_from_json(records, self.staging, job_config=job_config).result()

        sql = f"""
        BEGIN TRANSACTION;
        DELETE FROM `{self.target}` WHERE date = @day AND platform = @platform;
        INSERT INTO `{self.target}` SELECT * FROM `{self.staging}`;
        COMMIT TRANSACTION;
        """
        params = [
            bigquery.ScalarQueryParameter("day", "DATE", day),
            bigquery.ScalarQueryParameter("platform", "STRING", platform),
        ]
        self.client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        return len(records)
