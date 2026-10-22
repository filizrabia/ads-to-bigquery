"""One normalized row format for every ad platform.

Each source maps its own API response into ``AdRow``. Everything downstream
(loading, dbt models, dashboards) only knows this schema, so adding a new
platform means writing one mapper, not touching the warehouse.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import date


@dataclass(frozen=True)
class AdRow:
    date: date
    platform: str
    account_id: str
    campaign_id: str
    campaign_name: str
    ad_group_id: str
    ad_group_name: str
    impressions: int
    clicks: int
    spend: float
    conversions: float
    conversion_value: float
    currency: str

    def __post_init__(self):
        if self.impressions < 0 or self.clicks < 0 or self.spend < 0:
            raise ValueError(f"negative metric in row for campaign {self.campaign_id} on {self.date}")
        if self.clicks > self.impressions:
            raise ValueError(f"clicks > impressions for campaign {self.campaign_id} on {self.date}")
        if len(self.currency) != 3:
            raise ValueError(f"currency must be an ISO code, got {self.currency!r}")

    def to_record(self) -> dict:
        rec = asdict(self)
        rec["date"] = self.date.isoformat()
        return rec


COLUMNS = [f.name for f in fields(AdRow)]

# BigQuery schema, kept next to the dataclass so the two cannot drift apart silently.
BIGQUERY_SCHEMA = [
    ("date", "DATE"),
    ("platform", "STRING"),
    ("account_id", "STRING"),
    ("campaign_id", "STRING"),
    ("campaign_name", "STRING"),
    ("ad_group_id", "STRING"),
    ("ad_group_name", "STRING"),
    ("impressions", "INT64"),
    ("clicks", "INT64"),
    ("spend", "NUMERIC"),
    ("conversions", "FLOAT64"),
    ("conversion_value", "NUMERIC"),
    ("currency", "STRING"),
]

assert [c for c, _ in BIGQUERY_SCHEMA] == COLUMNS, "BigQuery schema out of sync with AdRow"
