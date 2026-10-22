"""Deterministic fake source, so the whole pipeline runs locally without API keys.

Numbers follow simple but realistic patterns: weekend dips, a slow upward trend,
and campaigns with different efficiency (retargeting converts best, broad
prospecting worst).
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator
from datetime import date

from ..schema import AdRow

# campaign id -> (name, ad groups, CPM in EUR, CTR, conversion rate, avg order value)
CAMPAIGNS = {
    "c-100": ("Prospecting | Broad", ["Lookalike 1%", "Interests: Running"], 7.0, 0.011, 0.018, 62.0),
    "c-200": ("Retargeting | 30d", ["Site visitors", "Add to cart"], 11.0, 0.021, 0.045, 71.0),
    "c-300": ("Brand | Always-on", ["Core audience"], 9.0, 0.028, 0.038, 66.0),
}

PLATFORM_SCALE = {"meta": 1.0, "google_ads": 0.7, "fake": 1.0}


class FakeAdsSource:
    def __init__(self, platform: str = "fake", seed: int = 42):
        self.platform = platform
        self.seed = seed

    def fetch_day(self, day: date) -> Iterator[AdRow]:
        rng = random.Random(f"{self.seed}-{self.platform}-{day.isoformat()}")
        weekday = 0.82 if day.weekday() >= 5 else 1.0
        trend = 1 + 0.002 * (day - date(2026, 1, 1)).days
        season = 1 + 0.08 * math.sin(2 * math.pi * day.timetuple().tm_yday / 365)
        scale = PLATFORM_SCALE.get(self.platform, 1.0) * weekday * trend * season
        for cid, (cname, groups, cpm, ctr, cvr, aov) in CAMPAIGNS.items():
            for i, gname in enumerate(groups):
                impressions = int(rng.uniform(15_000, 25_000) * scale)
                clicks = int(impressions * ctr * rng.uniform(0.85, 1.15))
                spend = round(impressions / 1000 * cpm * rng.uniform(0.9, 1.1), 2)
                conversions = round(clicks * cvr * rng.uniform(0.7, 1.3), 1)
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
                    conversion_value=round(conversions * aov * rng.uniform(0.9, 1.1), 2),
                    currency="EUR",
                )
