from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import fakeredis

from site_generator.config import Settings
from site_generator.expiry_main import run_expiry_sweep
from site_generator.store import SiteDeploymentStore

from .fakes import StubDeployer


def _settings() -> Settings:
    return Settings(redis_url="redis://testing", vercel_token="fake-token")


def test_run_expiry_sweep_end_to_end_with_injected_redis_and_deployer():
    redis_client = fakeredis.FakeRedis()
    store = SiteDeploymentStore(redis_client)
    store.record("place-old", "https://old.vercel.app", "dpl_old")
    redis_client.hset(
        "site_deployment:place-old",
        "created_at",
        (datetime.now(timezone.utc) - timedelta(days=20)).isoformat(),
    )
    store.record("place-new", "https://new.vercel.app", "dpl_new")

    deployer = StubDeployer()
    settings = _settings()
    settings.expiry_days = 14

    with (
        patch("site_generator.expiry_main.Redis.from_url", return_value=redis_client),
        patch("site_generator.expiry_main.VercelDeployer", return_value=deployer),
    ):
        result = run_expiry_sweep(settings)

    assert result == {"deleted": 1, "kept": 1, "errors": 0}
    assert deployer.delete_calls == ["dpl_old"]
    assert store.get("place-old") is None
    assert store.get("place-new") is not None
