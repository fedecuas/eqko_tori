from site_generator.template import DISCLAIMER, render_teaser_html


def test_includes_noindex_always():
    html = render_teaser_html("Taquería El Buen Sazón", "+523312345678")

    assert 'name="robots" content="noindex, nofollow"' in html


def test_includes_the_agreed_disclaimer_text_verbatim():
    html = render_teaser_html("Taquería El Buen Sazón", "+523312345678")

    assert DISCLAIMER in html


def test_disclaimer_points_to_the_same_contact_channel_not_a_separate_address():
    # Acordado en la validación del Módulo 7: la baja se gestiona por el mismo canal de
    # contacto, no un email/telefono separado -- si esto cambia, romper el test a propósito
    # para forzar volver a pasar por la validación.
    assert "mismo medio" in DISCLAIMER
    assert "@" not in DISCLAIMER  # no hay una dirección de contacto separada


def test_never_includes_fake_review_text():
    html = render_teaser_html("Taquería El Buen Sazón", "+523312345678")

    assert "reseña" not in html.lower()


def test_escapes_business_name_to_avoid_html_injection():
    html = render_teaser_html('<script>alert(1)</script>', "+523312345678")

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_rating_note_is_optional_and_only_shown_when_given():
    without_rating = render_teaser_html("Taquería", "+523312345678")
    with_rating = render_teaser_html("Taquería", "+523312345678", rating_note="4.8 en Google Maps")

    assert '<p class="rating">' not in without_rating
    assert "4.8 en Google Maps" in with_rating
