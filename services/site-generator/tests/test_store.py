import fakeredis

from site_generator.store import SiteDeploymentStore


def test_record_then_get_round_trips():
    store = SiteDeploymentStore(fakeredis.FakeRedis())

    store.record("place-1", "https://abc.vercel.app", "dpl_1")
    deployment = store.get("place-1")

    assert deployment["landing_url"] == "https://abc.vercel.app"
    assert deployment["deployment_id"] == "dpl_1"
    assert "created_at" in deployment


def test_get_missing_place_id_returns_none():
    store = SiteDeploymentStore(fakeredis.FakeRedis())

    assert store.get("does-not-exist") is None


def test_list_all_returns_every_recorded_deployment():
    store = SiteDeploymentStore(fakeredis.FakeRedis())
    store.record("place-1", "https://a.vercel.app", "dpl_1")
    store.record("place-2", "https://b.vercel.app", "dpl_2")

    deployments = store.list_all()

    assert {d["place_id"] for d in deployments} == {"place-1", "place-2"}


def test_remove_clears_the_entry_and_the_index():
    store = SiteDeploymentStore(fakeredis.FakeRedis())
    store.record("place-1", "https://a.vercel.app", "dpl_1")

    store.remove("place-1")

    assert store.get("place-1") is None
    assert store.list_all() == []
