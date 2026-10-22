"""Command line entry point.

    # local run, no credentials needed
    python -m pipeline.run --source fake --target sqlite --start 2026-01-01 --end 2026-01-31

    # production: Meta Ads into BigQuery
    export META_ACCESS_TOKEN=...  META_ACCOUNT_ID=...
    python -m pipeline.run --source meta --target bigquery \
        --project my-gcp-project --dataset marketing --start 2026-01-01 --end 2026-01-31

By default the last ``--lookback`` days are re-pulled on every run, because ad
platforms keep restating conversions for several days after the fact.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import date, timedelta

from .load import BigQueryLoader, SQLiteLoader

log = logging.getLogger("pipeline")


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def build_source(name: str):
    if name == "fake":
        from .sources.fake import FakeAdsSource

        return FakeAdsSource()
    if name == "meta":
        import requests

        from .sources.meta import MetaAdsSource

        return MetaAdsSource(
            account_id=os.environ["META_ACCOUNT_ID"],
            access_token=os.environ["META_ACCESS_TOKEN"],
            session=requests.Session(),
            api_version=os.environ.get("META_API_VERSION", "v21.0"),
        )
    raise ValueError(f"unknown source {name!r}")


def run(source, loader, start: date, end: date) -> dict[date, int]:
    loaded = {}
    for day in daterange(start, end):
        rows = list(source.fetch_day(day))
        loaded[day] = loader.replace_slice(day, source.platform, rows)
        log.info("%s %s: %d rows", source.platform, day, loaded[day])
    return loaded


def main(argv=None):
    p = argparse.ArgumentParser(description="Load daily ad performance into the warehouse.")
    p.add_argument("--source", choices=["fake", "meta"], default="fake")
    p.add_argument("--target", choices=["sqlite", "bigquery"], default="sqlite")
    p.add_argument("--start", type=date.fromisoformat)
    p.add_argument("--end", type=date.fromisoformat)
    p.add_argument("--lookback", type=int, default=7, help="days to re-pull when --start is not given")
    p.add_argument("--sqlite-path", default="ads.db")
    p.add_argument("--project")
    p.add_argument("--dataset")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    end = args.end or date.today() - timedelta(days=1)
    start = args.start or end - timedelta(days=args.lookback - 1)

    source = build_source(args.source)
    if args.target == "bigquery":
        loader = BigQueryLoader(args.project, args.dataset)
        loader.ensure_table()
    else:
        loader = SQLiteLoader(args.sqlite_path)

    loaded = run(source, loader, start, end)
    log.info("done: %d days, %d rows", len(loaded), sum(loaded.values()))


if __name__ == "__main__":
    main()
