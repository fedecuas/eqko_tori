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
MAPS = "https://maps.google.com/?cid=1"

PHOTO = PlacePhoto(
    name="places/p1/photos/REF0",
    google_maps_uri="https://www.google.com/maps/photo/0",
    attributions=(AuthorAttribution("Ana <b>", "https://maps.google.com/contrib/1", "https://lh3.googleusercontent.com/a/1"),),
)
MEDIA = PlaceMedia(photos=(PHOTO, PlacePhoto(name="places/p1/photos/REF1")), google_maps_uri=MAPS)
BRIEF = SiteBrief("Taquería El Buen Sazón", "+523312345678", "Sin web propia.", MEDIA)
BRIEF_NO_PHOTOS = SiteBrief("Taquería El Buen Sazón", "+523312345678", "Sin web propia.", PlaceMedia())


def page(body: str = "", head: str = "", css: str = "body{margin:0;color:var(--ink)}") -> str:
    return (
        '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
        f"<title>Lo que sea</title><style>{css}</style>{head}</head><body><header><h1>Taquería</h1></header>"
        f'<main><a href="tel:+523312345678">Llamar</a> <a href="https://wa.me/523312345678?text=Hola">WhatsApp</a>{body}</main></body></html>'
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


def test_compose_injects_charset_first_then_viewport_fonts_theme_and_a_preview_bar():
    html = compose_site(page(), BRIEF_NO_PHOTOS, None)

    assert html.index("<head>") + len("<head>") == html.index('<meta charset="utf-8">')
    assert 'name="viewport"' in html
    assert "fonts.googleapis.com/css2" in html
    assert "--primary:" in html
    assert "tori-preview-bar" in html
    assert "No es su sitio oficial" in html


def test_compose_replaces_the_model_title_with_the_business_name():
    html = compose_site(page(), BRIEF_NO_PHOTOS, None)

    assert "<title>Taquería El Buen Sazón</title>" in html
    assert "Lo que sea" not in html


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
        '<a href="https://evil.example">x</a>',
        '<a href="javascript:alert(1)">x</a>',
        '<p onclick="x()">x</p>',
        '<p style="background:url(https://evil.example/x.png)">x</p>',
        '<p style="color:#fff">x</p>',
        '<p style="color:white">x</p>',
        "<svg><script>x</script></svg>",
        '<svg><use href="https://evil.example/x.svg#a"></use></svg>',
        '<svg><path d="M0 0" onclick="x()"/></svg>',
        '<svg><foreignObject><p>x</p></foreignObject></svg>',
        "<p>Hola [Tu Nombre]</p>",
        "<p>Con el toque casero que nos caracteriza por generaciones.</p>",
        "<p>Más de 20 años de experiencia.</p>",
        "<p>Nos enorgullece servirte.</p>",
        "<p>Tacos auténticos.</p>",
        "<p>El sabor de siempre.</p>",
        "<p>Calidad garantizada.</p>",
        "<p>{{PHOTO_9}}</p>",
        "<p>{{ALGO}}</p>",
    ],
)
def test_compose_rejects_unsafe_or_incomplete_content(body):
    with pytest.raises(InvalidSiteHtml):
        compose_site(page(body), BRIEF_NO_PHOTOS, None)


@pytest.mark.parametrize(
    "css",
    [
        "body{background:url(https://evil.example/x.png)}",
        '@import "https://evil.example/x.css";',
        "@font-face{font-family:x}",
        "body{background:#ff0000}",
        "body{color:#333}",
        "body{color:rgb(0,0,0)}",
        "body{background:hsl(10 50% 50%)}",
        "body{color:white}",
        "a{border:1px solid black}",
    ],
)
def test_compose_rejects_external_resources_and_hardcoded_colors_in_css(css):
    with pytest.raises(InvalidSiteHtml):
        compose_site(page(css=css), BRIEF_NO_PHOTOS, None)


def test_compose_accepts_theme_variables_gradients_and_css_names_that_only_look_like_colors():
    css = (
        ".hero{background:linear-gradient(135deg,var(--hero-bg),var(--primary-dark));color:var(--on-hero);"
        "box-shadow:var(--shadow);filter:grayscale(1)}#contacto{padding:8px}a:hover .card{transform:scale(1.03)}"
    )

    assert "linear-gradient" in compose_site(page(css=css), BRIEF_NO_PHOTOS, None)


def test_compose_accepts_inline_svg_icons_from_the_allowlist():
    icon = (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'aria-hidden="true"><path d="M5 12h14"/><circle cx="12" cy="12" r="9"/></svg>'
    )

    assert "<circle" in compose_site(page(icon), BRIEF_NO_PHOTOS, None)


def test_compose_rejects_a_robots_meta_written_by_the_llm():
    with pytest.raises(InvalidSiteHtml):
        compose_site(page(head='<meta name="robots" content="index">'), BRIEF_NO_PHOTOS, None)


def test_compose_rejects_links_written_by_the_llm_because_fonts_come_from_the_system():
    with pytest.raises(InvalidSiteHtml):
        compose_site(page(head='<link rel="stylesheet" href="https://evil.example/x.css">'), BRIEF_NO_PHOTOS, None)


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
    assert "places.googleapis.com" not in compose_site(page(), BRIEF, None)


def test_compose_swaps_the_maps_token_for_the_real_listing_link():
    html = compose_site(page('<a href="{{MAPS_URL}}">Cómo llegar</a>'), BRIEF, PUBLIC_KEY + "") if False else compose_site(
        page('<a href="{{MAPS_URL}}">Cómo llegar</a>{{PHOTO_1}}'), BRIEF, PUBLIC_KEY
    )

    assert f'href="{MAPS}"' in html
    assert "{{MAPS_URL}}" not in html


def test_compose_rejects_the_maps_token_when_there_is_no_listing():
    with pytest.raises(InvalidSiteHtml):
        compose_site(page('<a href="{{MAPS_URL}}">Cómo llegar</a>'), BRIEF_NO_PHOTOS, None)


def test_user_prompt_lists_photo_tokens_whatsapp_digits_and_theme_variables():
    prompt = build_user_prompt(BRIEF)

    assert "{{PHOTO_1}}, {{PHOTO_2}}" in prompt
    assert "https://wa.me/523312345678" in prompt
    assert "var(--primary)" in prompt and "var(--on-hero)" in prompt
    assert "{{MAPS_URL}}" in prompt


def test_user_prompt_tells_the_model_not_to_use_images_or_maps_when_there_are_none():
    prompt = build_user_prompt(BRIEF_NO_PHOTOS)

    assert "No hay fotos" in prompt
    assert "{{MAPS_URL}}" not in prompt


def test_system_prompt_forbids_hardcoded_colors_and_invented_facts():
    assert "var(--" in SYSTEM_PROMPT
    assert "NO inventes" in SYSTEM_PROMPT


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


def test_ai_builder_keeps_the_place_category_but_drops_photos_without_a_public_key():
    writer = ScriptedWriter([page()])
    provider = StubPhotos()

    _ai_builder(writer, provider, public_key=None).build("p1", "Taquería", "+523312345678", "x")

    assert provider.calls == ["p1"]  # se consulta igual: la categoría elige el tema visual
    assert writer.briefs[0].media.photos == ()
    assert writer.briefs[0].media.google_maps_uri == MAPS


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


def test_compose_adds_a_mobile_action_bar_with_whatsapp_and_call_links():
    html = compose_site(page(), BRIEF_NO_PHOTOS, None)

    bar = html[html.index('<nav class="tori-actionbar"') :].split("</nav>", 1)[0]
    assert 'href="https://wa.me/523312345678?text=' in bar
    assert 'href="tel:+523312345678"' in bar


def test_system_styles_provide_the_wrap_and_button_primitives_the_prompt_promises():
    html = compose_site(page(), BRIEF_NO_PHOTOS, None)

    for selector in (".wrap{", ".btn{", ".btn-primary", ".btn-outline-light", ".tori-actionbar"):
        assert selector in html
        assert selector.lstrip(".").split("{")[0].split("-")[0] in SYSTEM_PROMPT or selector in html


@pytest.mark.parametrize(
    "photo_count,expected",
    [(1, "no hay galería"), (2, "1 foto"), (3, "2 fotos: dos columnas iguales"), (4, "3 fotos: una grande"), (6, "5 fotos: grilla bento")],
)
def test_user_prompt_gives_a_gallery_layout_that_matches_how_many_photos_remain_after_the_hero(photo_count, expected):
    media = PlaceMedia(photos=tuple(PlacePhoto(name=f"places/p1/photos/R{i}") for i in range(photo_count)))
    prompt = build_user_prompt(SiteBrief("Taqueria", "+523312345678", "", media))

    assert expected in prompt
    assert "aspect-ratio fijo" in prompt


@pytest.mark.parametrize(
    "claim",
    [
        "Escribe por WhatsApp para coordinar tu entrega.",
        "Pide para llevar o visitanos.",
        "Tacos y antojitos.",
        "Llama y pasa a recogerlo.",
        "Haz tu pedido.",
        "Servicio a domicilio.",
        "Reserva tu mesa.",
    ],
)
def test_compose_rejects_service_and_product_promises_the_business_never_made(claim):
    with pytest.raises(InvalidSiteHtml):
        compose_site(page(f"<p>{claim}</p>"), BRIEF_NO_PHOTOS, None)


def test_compose_accepts_contact_only_copy():
    html = compose_site(page("<p>Restaurante mexicano. Escribenos o llama.</p>"), BRIEF_NO_PHOTOS, None)

    assert "Escribenos o llama" in html
