import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pipeline.load import SQLiteLoader
from pipeline.run import run
from pipeline.schema import AdRow
from pipeline.sources.base import RetryableError, with_retries
from pipeline.sources.fake import FakeAdsSource
from pipeline.sources.meta import MetaAdsSource


class FakeResponse:
    def __init__(self, body, status=200):
        self._body, self.status_code = body, status

    def json(self):
        return self._body


class FakeSession:
    """Plays back a fixed list of responses and records the requested URLs."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self.responses.pop(0)


def meta_row(adset_id, spend="10.50"):
    return {
        "account_id": "123",
        "account_currency": "EUR",
        "campaign_id": "c1",
        "campaign_name": "Prospecting | Broad",
        "adset_id": adset_id,
        "adset_name": "LAL",
        "impressions": "1000",
        "clicks": "25",
        "spend": spend,
        "actions": [{"action_type": "purchase", "value": "2"}, {"action_type": "link_click", "value": "25"}],
        "action_values": [{"action_type": "purchase", "value": "120.5"}],
    }


class SchemaTests(unittest.TestCase):
    def base(self, **kw):
        args = dict(
            date=date(2026, 1, 1), platform="meta", account_id="a", campaign_id="c", campaign_name="n",
            ad_group_id="g", ad_group_name="n", impressions=100, clicks=5, spend=1.0,
            conversions=0.0, conversion_value=0.0, currency="EUR",
        )
        args.update(kw)
        return AdRow(**args)

    def test_valid_row(self):
        self.assertEqual(self.base().to_record()["date"], "2026-01-01")

    def test_rejects_bad_rows(self):
        for bad in [dict(spend=-1), dict(clicks=200), dict(currency="euro")]:
            with self.assertRaises(ValueError):
                self.base(**bad)


class MetaSourceTests(unittest.TestCase):
    def test_paginates_and_maps_fields(self):
        session = FakeSession(
            [
                FakeResponse({"data": [meta_row("s1")], "paging": {"next": "https://graph.facebook.com/next-page"}}),
                FakeResponse({"data": [meta_row("s2", spend="5")]}),
            ]
        )
        src = MetaAdsSource("act_123", "token", session)
        rows = list(src.fetch_day(date(2026, 1, 1)))
        self.assertEqual([r.ad_group_id for r in rows], ["s1", "s2"])
        self.assertEqual(rows[0].conversions, 2.0)
        self.assertEqual(rows[0].conversion_value, 120.5)
        self.assertEqual(session.calls[1], ("https://graph.facebook.com/next-page", None))
        self.assertIn("act_123/insights", session.calls[0][0])

    def test_retries_on_rate_limit(self):
        session = FakeSession(
            [
                FakeResponse({}, status=429),
                FakeResponse({"error": {"code": 17, "message": "User request limit reached"}}),
                FakeResponse({"data": [meta_row("s1")]}),
            ]
        )
        sleeps = []
        src = MetaAdsSource("123", "token", session, sleep=sleeps.append)
        rows = list(src.fetch_day(date(2026, 1, 1)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(sleeps, [2.0, 4.0])

    def test_non_retryable_error_raises(self):
        session = FakeSession([FakeResponse({"error": {"code": 190, "message": "Invalid OAuth token"}})])
        with self.assertRaises(RuntimeError):
            list(MetaAdsSource("123", "bad", session).fetch_day(date(2026, 1, 1)))


class RetryTests(unittest.TestCase):
    def test_gives_up_after_attempts(self):
        def always_fail():
            raise RetryableError("nope")

        with self.assertRaises(RetryableError):
            with_retries(always_fail, attempts=3, sleep=lambda _: None)


class LoadTests(unittest.TestCase):
    def test_reloading_a_day_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "ads.db")
            loader = SQLiteLoader(db)
            src = FakeAdsSource()
            run(src, loader, date(2026, 1, 1), date(2026, 1, 3))
            run(src, loader, date(2026, 1, 2), date(2026, 1, 3))  # re-pull the last two days
            conn = sqlite3.connect(db)
            per_day = conn.execute("SELECT date, COUNT(*) FROM ads_daily GROUP BY date ORDER BY date").fetchall()
            self.assertEqual([n for _, n in per_day], [5, 5, 5])

    def test_reload_does_not_touch_other_platforms(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "ads.db")
            loader = SQLiteLoader(db)
            run(FakeAdsSource("meta"), loader, date(2026, 1, 1), date(2026, 1, 1))
            run(FakeAdsSource("google_ads"), loader, date(2026, 1, 1), date(2026, 1, 1))
            loader.replace_slice(date(2026, 1, 1), "meta", [])
            conn = sqlite3.connect(db)
            rows = dict(conn.execute("SELECT platform, COUNT(*) FROM ads_daily GROUP BY platform").fetchall())
            self.assertEqual(rows, {"google_ads": 5})


if __name__ == "__main__":
    unittest.main()
