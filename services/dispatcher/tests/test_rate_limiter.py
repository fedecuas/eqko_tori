import fakeredis

from dispatcher.rate_limiter import RateLimiter

from .fakes import FakeClock


def test_requests_within_the_limit_never_sleep():
    clock = FakeClock()
    limiter = RateLimiter(fakeredis.FakeRedis(), max_requests=3, window_seconds=1.0, sleep_fn=clock.sleep, clock_fn=clock.time)

    limiter.acquire("dispatch:airtable:alba")
    limiter.acquire("dispatch:airtable:alba")
    limiter.acquire("dispatch:airtable:alba")

    assert clock.sleeps == []


def test_exceeding_the_limit_sleeps_until_the_next_window():
    clock = FakeClock()
    limiter = RateLimiter(fakeredis.FakeRedis(), max_requests=2, window_seconds=1.0, sleep_fn=clock.sleep, clock_fn=clock.time)

    limiter.acquire("dispatch:airtable:alba")
    limiter.acquire("dispatch:airtable:alba")
    limiter.acquire("dispatch:airtable:alba")  # 3ra en la misma ventana -> debe esperar

    assert clock.sleeps == [1.0]
    assert clock.now == 1.0


def test_different_keys_have_independent_budgets():
    clock = FakeClock()
    redis_client = fakeredis.FakeRedis()
    limiter = RateLimiter(redis_client, max_requests=1, window_seconds=1.0, sleep_fn=clock.sleep, clock_fn=clock.time)

    limiter.acquire("dispatch:airtable:alba")
    limiter.acquire("dispatch:airtable:otro-tenant")  # key distinta -> no comparte balde

    assert clock.sleeps == []


def test_a_new_window_resets_the_budget():
    clock = FakeClock()
    redis_client = fakeredis.FakeRedis()
    limiter = RateLimiter(redis_client, max_requests=1, window_seconds=1.0, sleep_fn=clock.sleep, clock_fn=clock.time)

    limiter.acquire("dispatch:airtable:alba")
    clock.now = 1.5  # avanza a la siguiente ventana sin pasar por sleep_fn
    limiter.acquire("dispatch:airtable:alba")

    assert clock.sleeps == []
