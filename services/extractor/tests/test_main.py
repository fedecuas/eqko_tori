from tori_shared_types import STREAM_PLACE_EXTRACTED

from .conftest import INTERNAL_API_KEY

AUTH_HEADERS = {"X-Internal-Api-Key": INTERNAL_API_KEY}


def test_health_does_not_require_auth(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_run_without_api_key_is_rejected(client):
    response = client.post("/runs", json={"tenant_id": "alba", "query": "restaurantes"})
    assert response.status_code == 401


def test_create_run_with_wrong_api_key_is_rejected(client):
    response = client.post(
        "/runs",
        json={"tenant_id": "alba", "query": "restaurantes"},
        headers={"X-Internal-Api-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_create_run_responds_immediately_with_queued_run_id(client):
    response = client.post(
        "/runs",
        json={"tenant_id": "alba", "query": "restaurantes en Guadalajara"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["run_id"]


def test_run_completes_and_only_publishes_non_duplicate_places(client, redis_client, stub_places_provider):
    response = client.post(
        "/runs",
        json={"tenant_id": "alba", "query": "restaurantes en Guadalajara"},
        headers=AUTH_HEADERS,
    )
    run_id = response.json()["run_id"]

    status_response = client.get(f"/runs/{run_id}", headers=AUTH_HEADERS)
    assert status_response.status_code == 200
    run = status_response.json()

    assert run["status"] == "completed"
    assert int(run["places_found"]) == 2
    assert int(run["places_published"]) == 2
    assert int(run["places_duplicate"]) == 0

    stream_entries = redis_client.xrange(STREAM_PLACE_EXTRACTED)
    assert len(stream_entries) == 2


def test_second_run_with_same_places_is_all_duplicates(client, redis_client, stub_places_provider):
    first = client.post(
        "/runs",
        json={"tenant_id": "alba", "query": "restaurantes en Guadalajara"},
        headers=AUTH_HEADERS,
    )
    client.get(f"/runs/{first.json()['run_id']}", headers=AUTH_HEADERS)

    second = client.post(
        "/runs",
        json={"tenant_id": "alba", "query": "restaurantes en Guadalajara"},
        headers=AUTH_HEADERS,
    )
    run_id = second.json()["run_id"]
    run = client.get(f"/runs/{run_id}", headers=AUTH_HEADERS).json()

    assert run["status"] == "completed"
    assert int(run["places_found"]) == 2
    assert int(run["places_published"]) == 0
    assert int(run["places_duplicate"]) == 2

    # Solo los eventos del primer run llegaron al stream
    stream_entries = redis_client.xrange(STREAM_PLACE_EXTRACTED)
    assert len(stream_entries) == 2


def test_get_unknown_run_is_404(client):
    response = client.get("/runs/does-not-exist", headers=AUTH_HEADERS)
    assert response.status_code == 404


def test_invalid_request_body_is_rejected(client):
    response = client.post(
        "/runs",
        json={"tenant_id": "alba"},  # falta query
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422
