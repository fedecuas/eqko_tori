from agent_worker.phone import format_e164


def test_formats_valid_mexican_number_to_e164():
    assert format_e164("+52 33 1234 5678") == "+523312345678"


def test_returns_none_for_garbage_input():
    assert format_e164("not a phone number") is None


def test_returns_none_for_number_without_country_code():
    # phonenumbers.parse(raw, None) necesita el + con código de país -- si no viene así
    # desde Google Places, no podemos asumir una región y se descarta.
    assert format_e164("33 1234 5678") is None


def test_returns_none_for_invalid_number_with_plausible_format():
    assert format_e164("+52 00 0000 0000") is None
