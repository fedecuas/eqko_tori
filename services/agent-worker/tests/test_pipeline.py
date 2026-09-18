from datetime import datetime, timezone

from tori_shared_types import PlaceExtractedEvent

from agent_worker.pipeline import qualify

BASE_KWARGS = dict(
    run_id="run-1",
    tenant_id="alba",
    place_id="place-1",
    display_name="Taquería El Buen Sazón",
    formatted_address="Av. Siempre Viva 123",
    extracted_at=datetime.now(timezone.utc),
)


def test_qualifies_a_lead_without_website_and_with_valid_phone():
    event = PlaceExtractedEvent(
        **BASE_KWARGS, website_uri=None, international_phone_number="+52 33 1234 5678"
    )

    lead = qualify(event)

    assert lead is not None
    assert lead.phone_e164 == "+523312345678"
    assert lead.place_id == "place-1"


def test_rejects_a_business_with_a_website():
    event = PlaceExtractedEvent(
        **BASE_KWARGS, website_uri="https://tiene-sitio.com", international_phone_number="+523312345678"
    )

    assert qualify(event) is None


def test_rejects_a_business_without_phone():
    event = PlaceExtractedEvent(**BASE_KWARGS, website_uri=None, international_phone_number=None)

    assert qualify(event) is None


def test_rejects_a_business_with_an_unparseable_phone():
    event = PlaceExtractedEvent(
        **BASE_KWARGS, website_uri=None, international_phone_number="not a real phone"
    )

    assert qualify(event) is None
