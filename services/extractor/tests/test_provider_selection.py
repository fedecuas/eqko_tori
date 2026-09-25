import pytest

from app import dependencies
from app.config import Settings
from app.denue_client import DenueProvider
from app.places_client import GooglePlacesProvider


def _provider_for(monkeypatch, **settings):
    # `_env_file=None`: que un .env local con credenciales reales no cambie el resultado del test.
    monkeypatch.setattr(dependencies, "get_settings", lambda: Settings(_env_file=None, tori_internal_api_key="k", **settings))
    return dependencies.get_places_provider.__wrapped__()


def test_google_is_the_default_source(monkeypatch):
    provider = _provider_for(monkeypatch, google_places_api_key="g-key")

    assert isinstance(provider, GooglePlacesProvider)


def test_denue_is_selected_with_extraction_provider_and_its_token(monkeypatch):
    provider = _provider_for(monkeypatch, extraction_provider="denue", denue_token="d-token")

    assert isinstance(provider, DenueProvider)


def test_denue_without_a_token_fails_loudly_instead_of_falling_back_to_google(monkeypatch):
    with pytest.raises(RuntimeError, match="DENUE_TOKEN"):
        _provider_for(monkeypatch, extraction_provider="denue", google_places_api_key="g-key")


def test_google_without_a_key_points_at_the_denue_alternative(monkeypatch):
    with pytest.raises(RuntimeError, match="denue"):
        _provider_for(monkeypatch)
