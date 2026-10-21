"""Consistent scheduled discount calculation for catalog and checkout."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP


def active_discount_percent(percent: int | None, start_at: datetime | None,
                            end_at: datetime | None, now: datetime | None = None) -> int | None:
    if percent is None:
        return None
    now = now or datetime.now(timezone.utc)
    if start_at is not None and now < _utc(start_at):
        return None
    if end_at is not None and now >= _utc(end_at):
        return None
    return percent


def discounted_price(original: Decimal, percent: int | None) -> Decimal:
    if percent is None:
        return original
    return (original * (Decimal(100 - percent) / Decimal(100))).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
