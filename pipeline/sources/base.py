from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from datetime import date
from typing import Protocol, TypeVar

from ..schema import AdRow

log = logging.getLogger(__name__)
T = TypeVar("T")


class AdSource(Protocol):
    platform: str

    def fetch_day(self, day: date) -> Iterable[AdRow]:
        """Return all ad-group level rows for one day."""
        ...


class RetryableError(Exception):
    """Rate limits and temporary server errors: worth trying again."""


def with_retries(fn: Callable[[], T], attempts: int = 5, base_delay: float = 2.0, sleep=time.sleep) -> T:
    """Call ``fn`` with exponential backoff on ``RetryableError``."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except RetryableError as exc:
            if attempt == attempts:
                raise
            delay = base_delay * 2 ** (attempt - 1)
            log.warning("retryable error (%s), attempt %d/%d, sleeping %.0fs", exc, attempt, attempts, delay)
            sleep(delay)
    raise AssertionError("unreachable")
