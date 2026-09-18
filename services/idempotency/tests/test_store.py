import fakeredis

from idempotency import IdempotencyStore


def test_mark_if_new_is_true_the_first_time():
    store = IdempotencyStore(fakeredis.FakeRedis())

    assert store.mark_if_new("event:leadgen:abc123") is True


def test_mark_if_new_is_false_for_a_duplicate():
    redis_client = fakeredis.FakeRedis()
    store = IdempotencyStore(redis_client)

    store.mark_if_new("event:leadgen:abc123")

    assert store.mark_if_new("event:leadgen:abc123") is False


def test_different_keys_do_not_collide():
    store = IdempotencyStore(fakeredis.FakeRedis())

    assert store.mark_if_new("event:leadgen:abc123") is True
    assert store.mark_if_new("event:leadgen:def456") is True


def test_ttl_is_forwarded_to_redis():
    redis_client = fakeredis.FakeRedis()
    store = IdempotencyStore(redis_client, ttl_seconds=60)

    store.mark_if_new("event:leadgen:abc123")

    assert redis_client.ttl("event:leadgen:abc123") == 60
