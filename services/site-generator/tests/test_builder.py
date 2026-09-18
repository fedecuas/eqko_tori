import pytest

from site_generator.builder import (
    SYSTEM_PROMPT,
    AiSiteBuilder,
    GeminiSiteWriter,
    InvalidSiteHtml,
    SiteBrief,
    SiteWriter,
    StaticSiteBuilder,
    build_user_prompt,
    compose_site,
)
from site_generator.photos import AuthorAttribution, NoPhotosProvider, PhotosProvider, PlaceMedia, PlacePhoto
from site_generator.template import DISCLAIMER

PUBLIC_KEY = "public-key"

PHOTO = PlacePhoto(
    name="places/p1/photos/REF0",
    google_maps_uri="https://www.google.com/maps/photo/0",
    attributions=(AuthorAttribution("Ana <b>", "https://maps.google.com/contrib/1", "https://lh3.googleusercontent.com/a/1"),),
)
MEDIA = PlaceMedia(photos=(PHOTO, PlacePhoto(name="places/p1/photos/REF1")), google_maps_uri="https://maps.google.com/?cid=1")
BRIEF = SiteBrief("Taquería El Buen Sazón", "+523312345678", "Sin web propia.", MEDIA)
BRIEF_NO_PHOTOS = SiteBrief("Taquería El Buen Sazón", "+523312345678", "Sin web propia.", PlaceMedia())


def page(body: str = "", head: str = "", css: str = "body{margin:0}") -> str:
    return (
        '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
        f"<title>x</title><style>{css}</style>{head}</head><body><header><h1>Taquería</h1></header>"
        f'<main><a href="tel:+523312345678">Llamar</a> <a href="https://wa.me/523312345678">WhatsApp</a>{body}</main></body></html>'
    )


def test_compose_replaces_photo_tokens_with_live_google_urls_and_attribution():
    html = compose_site(page("{{PHOTO_1}}{{PHOTO_2}}"), BRIEF, PUBLIC_KEY)

    assert 'src="https://places.googleapis.com/v1/places/p1/photos/REF0/media?maxWidthPx=800&amp;key=public-key"' in html
    assert "places/p1/photos/REF1/media" in html
    assert 'href="https://maps.google.com/contrib/1"' in html
    assert 'href="https://www.google.com/maps/photo/0"' in html
    assert "{{" not in html


def test_compose_escapes_attribution_names_coming_from_google():
    html = compose_site(page("{{PHOTO_1}}"), BRIEF, PUBLIC_KEY)

    assert "Ana <b>" not in html
    assert "Ana &lt;b&gt;" in html


def test_compose_injects_noindex_disclaimer_and_google_attribution_itself():
    html = compose_site(page(), BRIEF_NO_PHOTOS, None)

    assert 'name="robots" content="noindex, nofollow"' in html
    assert DISCLAIMER in html
    assert "Google Maps" in html
    assert html.index("tori-footer") < html.index("</body>")


def test_compose_puts_noindex_inside_head_not_in_a_header_element():
    html = compose_site(page(), BRIEF_NO_PHOTOS, None)

    assert html.index('name="robots"') < html.index("</head>")


@pytest.mark.parametrize(
    "body",
    [
        "<script>alert(1)</script>",
        '<iframe src="https://evil.example"></iframe>',
        '<form action="https://evil.example"><input name="x"></form>',
        '<img src="https://evil.example/x.png">',
        "<svg></svg>",
        '<a href="https://evil.example">x</a>',
        '<a href="javascript:alert(1)">x</a>',
        '<p onclick="x()">x</p>',
        '<p style="background:url(https://evil.example/x.png)">x</p>',
        "<p>Hola [Tu Nombre]</p>",
        "<p>Con el toque casero que nos caracteriza por generaciones.</p>",
        "<p>Más de 20 años de experiencia.</p>",
        "<p>Nos enorgullece servirte.</p>",
        "<p>{{PHOTO_9}}</p>",
        "<p>{{ALGO}}</p>",
    ],
)
def test_compose_rejects_unsafe_or_incomplete_content(body):
    with pytest.raises(InvalidSiteHtml):
        compose_site(page(body), BRIEF_NO_PHOTOS, None)


def test_compose_rejects_external_css_urls_and_imports():
    with pytest.raises(InvalidSiteHtml):
        compose_site(page(css="body{background:url(https://evil.example/x.png)}"), BRIEF_NO_PHOTOS, None)
    with pytest.raises(InvalidSiteHtml):
        compose_site(page(css='@import "https://evil.example/x.css";'), BRIEF_NO_PHOTOS, None)


def test_compose_rejects_a_robots_meta_written_by_the_llm():
    with pytest.raises(InvalidSiteHtml):
        compose_site(page(head='<meta name="robots" content="index">'), BRIEF_NO_PHOTOS, None)


def test_compose_rejects_truncated_html():
    with pytest.raises(InvalidSiteHtml):
        compose_site("<!DOCTYPE html><html><head></head><body><main>corta", BRIEF_NO_PHOTOS, None)


def test_compose_rejects_a_page_with_only_a_header_element_and_no_head():
    with pytest.raises(InvalidSiteHtml):
        compose_site("<html><body><header>x</header></body></html>", BRIEF_NO_PHOTOS, None)


def test_compose_requires_using_at_least_one_photo_when_photos_exist():
    with pytest.raises(InvalidSiteHtml):
        compose_site(page(), BRIEF, PUBLIC_KEY)


def test_compose_rejects_repeated_photo_tokens():
    with pytest.raises(InvalidSiteHtml):
        compose_site(page("{{PHOTO_1}}{{PHOTO_1}}"), BRIEF, PUBLIC_KEY)


def test_compose_ignores_photos_when_there_is_no_public_key():
    # Sin key pública no se puede armar una URL válida: cualquier marcador queda fuera de rango.
    with pytest.raises(InvalidSiteHtml):
        compose_site(page("{{PHOTO_1}}"), BRIEF, None)
    assert "<img" not in compose_site(page(), BRIEF, None)


def test_user_prompt_lists_photo_tokens_and_whatsapp_digits():
    prompt = build_user_prompt(BRIEF)

    assert "{{PHOTO_1}}, {{PHOTO_2}}" in prompt
    assert "https://wa.me/523312345678" in prompt
    assert "Sin web propia." in prompt


def test_user_prompt_tells_the_model_not_to_use_images_when_there_are_no_photos():
    assert "No hay fotos" in build_user_prompt(BRIEF_NO_PHOTOS)


class ScriptedWriter(SiteWriter):
    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.briefs = []

    def write(self, brief):
        self.briefs.append(brief)
        output = self._outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


class StubPhotos(PhotosProvider):
    def __init__(self):
        self.calls = []

    def fetch(self, place_id):
        self.calls.append(place_id)
        return MEDIA


def _ai_builder(writer, provider=None, public_key=PUBLIC_KEY, max_attempts=2):
    return AiSiteBuilder(writer, provider or StubPhotos(), public_key, max_attempts=max_attempts)


def test_ai_builder_returns_the_composed_page_with_photos():
    writer = ScriptedWriter([page("{{PHOTO_1}}")])
    provider = StubPhotos()

    html = _ai_builder(writer, provider).build("p1", "Taquería", "+523312345678", "Sin web.")

    assert provider.calls == ["p1"]
    assert len(writer.briefs[0].media.photos) == 2
    assert "places.googleapis.com" in html


def test_ai_builder_retries_once_on_invalid_html_then_succeeds():
    writer = ScriptedWriter(["<script>x</script>", page()])

    html = _ai_builder(writer, NoPhotosProvider(), public_key=None).build("p1", "Taquería", "+523312345678", "x")

    assert len(writer.briefs) == 2
    assert DISCLAIMER in html


def test_ai_builder_falls_back_to_the_static_template_after_max_attempts():
    writer = ScriptedWriter(["<script>x</script>", "<script>y</script>"])

    html = _ai_builder(writer, NoPhotosProvider(), public_key=None).build("p1", "Taquería", "+523312345678", "x")

    assert html == StaticSiteBuilder().build("p1", "Taquería", "+523312345678", "x")


def test_ai_builder_propagates_llm_api_errors_for_the_retry_cycle():
    writer = ScriptedWriter([RuntimeError("gemini down")])

    with pytest.raises(RuntimeError):
        _ai_builder(writer, NoPhotosProvider(), public_key=None).build("p1", "Taquería", "+523312345678", "x")


def test_ai_builder_does_not_fetch_photos_without_a_public_key():
    writer = ScriptedWriter([page()])
    provider = StubPhotos()

    _ai_builder(writer, provider, public_key=None).build("p1", "Taquería", "+523312345678", "x")

    assert provider.calls == []
    assert writer.briefs[0].media.photos == ()


def test_gemini_writer_sends_the_system_prompt_and_strips_a_markdown_fence():
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return {"choices": [{"message": {"content": "```html\n<html>ok</html>\n```"}}]}

    writer = GeminiSiteWriter(model="gemini/x", api_key="k", completion=fake_completion)

    assert writer.write(BRIEF_NO_PHOTOS) == "<html>ok</html>"
    assert captured["model"] == "gemini/x"
    assert captured["api_key"] == "k"
    assert captured["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert "Taquería El Buen Sazón" in captured["messages"][1]["content"]


def test_avatar_is_sized_inline_so_llm_css_for_photo_images_cannot_blow_it_up():
    html = compose_site(page("{{PHOTO_1}}"), BRIEF, PUBLIC_KEY)

    avatar = html[html.index('class="tori-avatar"') :].split(">", 1)[0]
    assert "width:16px" in avatar and "height:16px" in avatar


def test_footer_source_line_does_not_reuse_the_photo_attribution_class():
    # Gemini estiliza .tori-attribution (a veces como overlay absoluto); el footer no debe heredarlo.
    html = compose_site(page(), BRIEF_NO_PHOTOS, None)

    footer = html[html.index('<footer class="tori-footer">') :]
    assert "tori-attribution" not in footer
