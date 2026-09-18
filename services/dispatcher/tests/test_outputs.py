import json
from datetime import datetime, timezone

import httpx
import pytest
from tori_shared_types import LeadApprovedEvent

from dispatcher.outputs import AirtableOutput, GoogleSheetsOutput, StaticOutputRouter

EVENT = LeadApprovedEvent(
    run_id="run-1",
    tenant_id="alba",
    place_id="place-1",
    display_name="Taquería El Buen Sazón",
    phone_e164="+523312345678",
    message_text="Hola! Vimos tu taquería...",
    gap_analysis="Sin web propia.",
    model="stub-model",
    approved_at=datetime.now(timezone.utc),
)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_airtable_upsert_sends_performupsert_on_place_id():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"records": []})

    output = AirtableOutput(access_token="fake-token", base_id="appXXX", table_name="Leads", client=_client(handler))

    output.upsert(EVENT)

    request = captured["request"]
    assert request.method == "PATCH"
    assert str(request.url) == "https://api.airtable.com/v0/appXXX/Leads"
    assert request.headers["Authorization"] == "Bearer fake-token"

    body = captured["body"]
    assert body["performUpsert"] == {"fieldsToMergeOn": ["place_id"]}
    fields = body["records"][0]["fields"]
    assert fields["place_id"] == "place-1"
    assert fields["message_text"] == "Hola! Vimos tu taquería..."


def test_airtable_upsert_raises_on_http_error():
    output = AirtableOutput(
        access_token="fake-token",
        base_id="appXXX",
        table_name="Leads",
        client=_client(lambda request: httpx.Response(422, json={"error": "bad request"})),
    )

    with pytest.raises(httpx.HTTPStatusError):
        output.upsert(EVENT)


def test_sheets_upsert_appends_when_place_id_not_found():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"values": [["place_id"], ["place-other"]]})
        return httpx.Response(200, json={"updates": {"updatedRows": 1}})

    output = GoogleSheetsOutput(access_token="fake-token", spreadsheet_id="sheet-1", client=_client(handler))

    output.upsert(EVENT)

    get_call, write_call = calls
    assert get_call.method == "GET"
    assert "Leads!A:A" in str(get_call.url)
    assert write_call.method == "POST"
    assert "append" in str(write_call.url)
    body = json.loads(write_call.content)
    assert body["values"][0][0] == "place-1"


def test_sheets_upsert_updates_existing_row_in_place():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"values": [["place_id"], ["place-1"]]})
        return httpx.Response(200, json={"updatedRows": 1})

    output = GoogleSheetsOutput(access_token="fake-token", spreadsheet_id="sheet-1", client=_client(handler))

    output.upsert(EVENT)

    get_call, write_call = calls
    assert write_call.method == "PUT"
    assert "Leads!A2:G2" in str(write_call.url)


def test_static_output_router_raises_for_unknown_tenant():
    router = StaticOutputRouter({})

    with pytest.raises(ValueError, match="alba"):
        router.get_output("alba")
