"""Meta (Facebook / Instagram) Ads via the Marketing API insights endpoint."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date

from ..schema import AdRow
from .base import RetryableError, with_retries

# Error codes Meta uses for throttling and temporary problems.
_RETRYABLE_CODES = {1, 2, 4, 17, 32, 341, 613, 80000, 80004}

FIELDS = [
    "account_id",
    "account_currency",
    "campaign_id",
    "campaign_name",
    "adset_id",
    "adset_name",
    "impressions",
    "clicks",
    "spend",
    "actions",
    "action_values",
]


def _action_total(items: list[dict] | None, action_type: str) -> float:
    return sum(float(i.get("value", 0)) for i in items or [] if i.get("action_type") == action_type)


class MetaAdsSource:
    platform = "meta"

    def __init__(
        self,
        account_id: str,
        access_token: str,
        session,
        api_version: str = "v21.0",
        conversion_action: str = "purchase",
        sleep=None,
    ):
        self.account_id = account_id.removeprefix("act_")
        self.access_token = access_token
        self.session = session  # a requests.Session, or anything with .get()
        self.base_url = f"https://graph.facebook.com/{api_version}"
        self.conversion_action = conversion_action
        self._sleep = sleep

    def _get(self, url: str, params: dict | None) -> dict:
        def call():
            resp = self.session.get(url, params=params, timeout=60)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise RetryableError(f"HTTP {resp.status_code}")
            body = resp.json()
            if "error" in body:
                err = body["error"]
                if err.get("code") in _RETRYABLE_CODES or err.get("is_transient"):
                    raise RetryableError(f"Meta error {err.get('code')}: {err.get('message')}")
                raise RuntimeError(f"Meta API error {err.get('code')}: {err.get('message')}")
            return body

        kwargs = {"sleep": self._sleep} if self._sleep else {}
        return with_retries(call, **kwargs)

    def _pages(self, day: date) -> Iterator[dict]:
        url = f"{self.base_url}/act_{self.account_id}/insights"
        params = {
            "access_token": self.access_token,
            "level": "adset",
            "fields": ",".join(FIELDS),
            "time_range": json.dumps({"since": day.isoformat(), "until": day.isoformat()}),
            "time_increment": 1,
            "limit": 500,
        }
        while url:
            body = self._get(url, params)
            yield from body.get("data", [])
            # The "next" URL already carries all query parameters, including the token.
            url, params = body.get("paging", {}).get("next"), None

    def fetch_day(self, day: date) -> Iterator[AdRow]:
        for r in self._pages(day):
            yield AdRow(
                date=day,
                platform=self.platform,
                account_id=str(r.get("account_id", self.account_id)),
                campaign_id=r["campaign_id"],
                campaign_name=r.get("campaign_name", ""),
                ad_group_id=r["adset_id"],
                ad_group_name=r.get("adset_name", ""),
                impressions=int(r.get("impressions", 0)),
                clicks=int(r.get("clicks", 0)),
                spend=round(float(r.get("spend", 0)), 2),
                conversions=_action_total(r.get("actions"), self.conversion_action),
                conversion_value=round(_action_total(r.get("action_values"), self.conversion_action), 2),
                currency=r.get("account_currency", "EUR"),
            )
