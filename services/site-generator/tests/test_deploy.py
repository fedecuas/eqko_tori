import json

import httpx
import pytest

from site_generator.deploy import VercelDeployer, slug_for


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_deploy_sends_the_file_and_parses_the_result():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "dpl_abc123", "url": "tori-leads-xyz.vercel.app"})

    deployer = VercelDeployer(token="fake-token", project_name="tori-leads", client=_client(handler))

    result = deployer.deploy("<html></html>", "xyz")

    assert result.deployment_id == "dpl_abc123"
    assert result.url == "https://tori-leads-xyz.vercel.app"

    request = captured["request"]
    assert request.method == "POST"
    assert request.headers["Authorization"] == "Bearer fake-token"
    body = captured["body"]
    # Al proyecto existente, no uno nuevo por lead -- ver docstring de VercelDeployer sobre
    # por qué (403 "permission to create a project", confirmado contra la API real).
    assert body["name"] == "tori-leads"
    assert body["project"] == "tori-leads"
    assert body["meta"] == {"tori_place_slug": "xyz"}
    assert body["files"] == [{"file": "index.html", "data": "<html></html>"}]


def test_deploy_raises_on_http_error():
    deployer = VercelDeployer(
        token="fake-token", project_name="tori-leads",
        client=_client(lambda request: httpx.Response(401, json={"error": "invalid token"})),
    )

    with pytest.raises(httpx.HTTPStatusError):
        deployer.deploy("<html></html>", "xyz")


def test_delete_calls_the_right_endpoint():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={})

    deployer = VercelDeployer(token="fake-token", project_name="tori-leads", client=_client(handler))

    deployer.delete("dpl_abc123")

    request = captured["request"]
    assert request.method == "DELETE"
    assert "dpl_abc123" in str(request.url)


def test_delete_is_a_noop_when_already_gone():
    deployer = VercelDeployer(
        token="fake-token", project_name="tori-leads",
        client=_client(lambda request: httpx.Response(404)),
    )

    deployer.delete("dpl_does_not_exist")  # no debe levantar


def test_slug_for_is_stable_and_not_derived_from_the_business_name():
    assert slug_for("place-1") == slug_for("place-1")
    assert slug_for("place-1") != slug_for("place-2")
    assert "place" not in slug_for("place-1")
