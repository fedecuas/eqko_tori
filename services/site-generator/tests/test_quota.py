from datetime import datetime, timezone

import fakeredis

from site_generator.quota import WeeklyQuota


def _clock_at(iso_date: str):
    year, month, day = (int(part) for part in iso_date.split("-"))
    return lambda: datetime(year, month, day, tzinfo=timezone.utc)


def test_allows_up_to_the_weekly_limit():
    quota = WeeklyQuota(fakeredis.FakeRedis(), max_per_week=3, clock_fn=_clock_at("2026-09-18"))

    assert quota.try_consume() is True
    assert quota.try_consume() is True
    assert quota.try_consume() is True


def test_denies_once_the_weekly_limit_is_reached():
    quota = WeeklyQuota(fakeredis.FakeRedis(), max_per_week=2, clock_fn=_clock_at("2026-09-18"))

    quota.try_consume()
    quota.try_consume()

    assert quota.try_consume() is False


def test_different_weeks_have_independent_budgets():
    redis_client = fakeredis.FakeRedis()
    quota_week_one = WeeklyQuota(redis_client, max_per_week=1, clock_fn=_clock_at("2026-09-18"))
    quota_week_two = WeeklyQuota(redis_client, max_per_week=1, clock_fn=_clock_at("2026-09-28"))

    assert quota_week_one.try_consume() is True
    assert quota_week_one.try_consume() is False  # semana 1 agotada
    assert quota_week_two.try_consume() is True  # semana 2, cupo aparte
