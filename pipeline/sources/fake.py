"""Deterministic fake source, so the whole pipeline runs locally without API keys."""

from __future__ import annotations

import random
from collections.abc import Iterator
from datetime import date

from ..schema import AdRow

CAMPAIGNS = {
    "c-100": ("Prospecting | Broad", ["Lookalike 1%", "Interests: Running"]),
    "c-200": ("Retargeting | 30d", ["Site visitors", "Add to cart"]),
    "c-300": ("Brand | Search", ["Exact match"]),
}


class FakeAdsSource:
    def __init__(self, platform: str = "fake", seed: int = 42):
        self.platform = platform
        self.seed = seed

    def fetch_day(self, day: date) -> Iterator[AdRow]:
        rng = random.Random(f"{self.seed}-{self.platform}-{day.isoformat()}")
        for cid, (cname, groups) in CAMPAIGNS.items():
            for i, gname in enumerate(groups):
                impressions = rng.randint(2_000, 40_000)
                clicks = int(impressions * rng.uniform(0.005, 0.03))
                spend = round(impressions / 1000 * rng.uniform(4, 12), 2)
                conversions = round(clicks * rng.uniform(0.01, 0.06), 1)
                yield AdRow(
                    date=day,
                    platform=self.platform,
                    account_id="demo-account",
                    campaign_id=cid,
                    campaign_name=cname,
                    ad_group_id=f"{cid}-g{i}",
                    ad_group_name=gname,
                    impressions=impressions,
                    clicks=clicks,
                    spend=spend,
                    conversions=conversions,
                    conversion_value=round(conversions * rng.uniform(40, 90), 2),
                    currency="EUR",
                )
