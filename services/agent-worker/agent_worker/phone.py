import phonenumbers


def format_e164(raw: str) -> str | None:
    """None si el número no se puede parsear o no es válido — se trata como negocio
    descalificado, no como error de procesamiento (ver pipeline.qualify)."""
    try:
        parsed = phonenumbers.parse(raw, None)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
