import html as html_lib
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from html.parser import HTMLParser

from .photos import PhotosProvider, PlaceMedia, PlacePhoto, photo_media_url
from .template import DISCLAIMER, render_teaser_html

logger = logging.getLogger(__name__)

NOINDEX_META = '<meta name="robots" content="noindex, nofollow">'

BASELINE_CSS = (
    "<style>"
    ".tori-photo{margin:0}.tori-photo img{display:block;max-width:100%;height:auto}"
    ".tori-attribution{font-size:12px;color:#666;line-height:1.4}.tori-attribution a{color:inherit}"
    ".tori-footer{position:static;display:block;font-size:13px;color:#555;background:#fff;"
    "border-top:1px solid #eee;padding:16px 24px;margin:0;text-align:center}"
    ".tori-footer p{margin:6px 0}.tori-footer a{color:inherit}"
    "</style>"
)

SYSTEM_PROMPT = """Sos un diseñador y desarrollador web senior. Generá UN archivo HTML completo (una sola \
página) que sirva como vista previa de cómo podría verse el sitio propio de un negocio local que hoy no \
tiene uno. Respondé SOLO con el HTML (de <!DOCTYPE html> a </html>), sin markdown ni explicaciones.

Calidad de UI/UX:
- Mobile-first y responsive: meta viewport, layouts con flex/grid, sin scroll horizontal (pensalo a 360px y a 1280px).
- Jerarquía visual clara: hero con el nombre del negocio y una llamada a la acción principal visible sin scroll; \
secciones con espaciado generoso; tipografía del sistema (system-ui), cuerpo >= 16px; contraste AA.
- Paleta coherente de 2-3 colores según el tipo de negocio que se infiera del nombre, en variables CSS (:root).
- Contraste: en cada sección definí JUNTOS el color de fondo y el de texto (relación >= 4.5:1). No existen imágenes \
de fondo (url() está prohibido): el fondo del hero es un color sólido o un gradiente CSS, y las fotos van en el \
flujo de la página con los marcadores. Nunca texto blanco sobre fondo claro ni texto oscuro sobre fondo oscuro.
- Accesible: HTML semántico (header, main, section), un solo h1, foco visible en enlaces y botones.
- CTAs grandes y tocables (>= 44px): enlace tel: con el teléfono dado y enlace de WhatsApp https://wa.me/<solo dígitos>.
- Sin JavaScript. Todo el CSS en un único <style> dentro de <head>. Sin fuentes ni recursos externos.

Contenido, reglas estrictas:
- Usá SOLO los datos dados (nombre, teléfono, análisis). NO inventes horarios, precios, dirección, menú, platillos, \
reseñas, testimonios, premios, años de experiencia ni cifras. Donde una web real mostraría eso, poné secciones de \
muestra con texto genérico honesto (ej. "Aquí irá tu menú") marcadas visiblemente como "Ejemplo".
- NO afirmes nada sobre el negocio que no esté en los datos: ni historia, tradición o "generaciones", ni calidad, \
ingredientes, recetas, ambiente, trato ("familiar", "artesanal", "casero", "los mejores"), ni que "nos enorgullece". \
Una sección "Nosotros" solo puede ser texto de muestra explícito ("Aquí contarás tu historia"). El subtítulo del \
hero debe ser neutro: qué es el negocio, sin adjetivos de calidad.
- Español de México, tono cercano y profesional.
- Nada de placeholders entre corchetes (ej. [Tu Nombre]).
- Incluí una sección breve "Por qué una web propia" basada en el análisis dado, dirigida al dueño en positivo.

Prohibido: <script>, <iframe>, <form>, <img>, <svg>, <link>, url(...) en CSS, atributos on*, y enlaces que no sean \
tel:, https://wa.me/ o anclas internas (#). No incluyas disclaimer, footer ni meta robots: el sistema los agrega."""

_FORBIDDEN_TAGS = {
    "script", "iframe", "object", "embed", "form", "input", "textarea", "select", "img", "svg", "picture",
    "source", "video", "audio", "canvas", "link", "base", "frame", "frameset", "applet", "math",
}
_URL_ATTRS = {"src", "srcset", "action", "formaction", "poster", "data", "background", "xlink:href"}
_INVENTED_CLAIMS = re.compile(
    r"generaci[oó]n|desde\s+(?:el\s+)?\d{4}|\d+\s+a[ñn]os|a[ñn]os de (?:experiencia|tradici)|galardon|premiad|"
    r"\bel mejor\b|\blos mejores\b|n[uú]mero\s*1|#1|enorgullec",
    re.IGNORECASE,
)
_PHOTO_TOKEN = re.compile(r"\{\{PHOTO_(\d+)\}\}")


class InvalidSiteHtml(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class SiteBrief:
    display_name: str
    phone_e164: str
    gap_analysis: str
    media: PlaceMedia


def build_user_prompt(brief: SiteBrief) -> str:
    digits = re.sub(r"\D", "", brief.phone_e164)
    photo_count = len(brief.media.photos)
    if photo_count:
        tokens = ", ".join(f"{{{{PHOTO_{i}}}}}" for i in range(1, photo_count + 1))
        photos = (
            f"Hay {photo_count} foto(s) reales del negocio. Colocalas con los marcadores {tokens}, cada uno una sola "
            "vez, escrito tal cual, como elemento suelto dentro de un contenedor de tu layout (hero o galería). El "
            'sistema reemplaza cada marcador por <figure class="tori-photo"><img ...><figcaption '
            'class="tori-attribution">...</figcaption></figure>. Estilizá con CSS .tori-photo, .tori-photo > img '
            "(ej. width:100%, aspect-ratio, object-fit:cover, border-radius) y .tori-attribution. No escribas <img> "
            "vos. Usá al menos una foto."
        )
    else:
        photos = "No hay fotos: no uses <img> ni marcadores; diseñá con color, tipografía y formas CSS."
    return (
        f"Negocio: {brief.display_name}\n"
        f"Teléfono: {brief.phone_e164} (WhatsApp: https://wa.me/{digits})\n"
        f"Análisis de brecha digital (base para la sección \"Por qué una web propia\"): {brief.gap_analysis}\n"
        f"Fotos: {photos}"
    )


def _has_css_url(css: str) -> bool:
    return bool(re.search(r"url\s*\(|@import|expression\s*\(|javascript:", css, re.IGNORECASE))


def _href_allowed(value: str) -> bool:
    return value.startswith(("tel:", "https://wa.me/", "#"))


class _Auditor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.problems: list[str] = []
        self.visible_text: list[str] = []
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _FORBIDDEN_TAGS:
            self.problems.append(f"etiqueta prohibida <{tag}>")
        if tag == "style":
            self._in_style = True
        attr_map = {name: (value or "") for name, value in attrs}
        if tag == "meta" and (attr_map.get("name", "").lower() == "robots" or "http-equiv" in attr_map):
            self.problems.append("meta robots/http-equiv no permitido (lo agrega el sistema)")
        for name, value in attr_map.items():
            if name.startswith("on"):
                self.problems.append(f"atributo de evento {name}")
            elif name == "style" and _has_css_url(value):
                self.problems.append("url()/@import en style inline")
            elif name == "href" and (tag != "a" or not _href_allowed(value)):
                self.problems.append(f"href no permitido: {value[:60]}")
            elif name in _URL_ATTRS:
                self.problems.append(f"atributo {name} no permitido en <{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_style:
            if _has_css_url(data):
                self.problems.append("url()/@import en <style>")
        else:
            self.visible_text.append(data)


def _https(value: str | None) -> str | None:
    return value if value and value.startswith("https://") else None


def _render_figure(photo: PlacePhoto, display_name: str, public_key: str) -> str:
    src = html_lib.escape(photo_media_url(photo.name, public_key), quote=True)
    alt = html_lib.escape(f"Foto de {display_name}", quote=True)
    credits = []
    for author in photo.attributions:
        avatar = _https(author.photo_uri)
        # Estilo inline (no solo clase): el CSS que escribe Gemini para `.tori-photo img` no debe
        # poder agrandar el avatar hasta tapar la foto.
        avatar_html = (
            f'<img class="tori-avatar" src="{html_lib.escape(avatar, quote=True)}" alt="" width="16" height="16" '
            'style="width:16px;height:16px;border-radius:50%;vertical-align:middle;margin-right:4px;'
            'object-fit:cover;aspect-ratio:1">'
            if avatar
            else ""
        )
        name = html_lib.escape(author.display_name)
        profile = _https(author.uri)
        name_html = f'<a href="{html_lib.escape(profile, quote=True)}" rel="noopener">{name}</a>' if profile else name
        credits.append(f"{avatar_html}{name_html}")
    source = _https(photo.google_maps_uri)
    if source:
        credits.append(f'<a href="{html_lib.escape(source, quote=True)}" rel="noopener">Ver en Google Maps</a>')
    caption = f'<figcaption class="tori-attribution">Foto: {" · ".join(credits)}</figcaption>' if credits else ""
    return f'<figure class="tori-photo"><img src="{src}" alt="{alt}" loading="lazy" referrerpolicy="origin">{caption}</figure>'


def _render_footer(media: PlaceMedia) -> str:
    maps_uri = _https(media.google_maps_uri)
    source = (
        f'<a href="{html_lib.escape(maps_uri, quote=True)}" rel="noopener">Google Maps</a>' if maps_uri else "Google Maps"
    )
    return (
        f'<footer class="tori-footer"><p>{html_lib.escape(DISCLAIMER)}</p>'
        f'<p class="tori-source">Datos y fotos: {source}</p></footer>'
    )


def _strip_code_fence(content: str) -> str:
    text = content.strip()
    fenced = re.match(r"^```(?:html)?\s*\n(.*)\n```$", text, re.DOTALL | re.IGNORECASE)
    return fenced.group(1).strip() if fenced else text


def compose_site(raw_html: str, brief: SiteBrief, public_key: str | None) -> str:
    """El HTML de Gemini nunca se despliega tal cual: se audita (sin scripts/forms/imágenes
    propias/enlaces externos) y el sistema inyecta lo que NO se le puede delegar al LLM —
    `noindex`, disclaimer literal, atribución de Google y las etiquetas <img> de las fotos
    (siempre apuntando en vivo a Google, nunca a un archivo nuestro)."""
    problems: list[str] = []
    lowered = raw_html.lower()
    if not re.search(r"<head[\s>]", lowered):
        problems.append("HTML incompleto: falta <head>")
    for marker in ("</head>", "<body", "</body>", "</html>"):
        if marker not in lowered:
            problems.append(f"HTML incompleto: falta {marker}")

    auditor = _Auditor()
    auditor.feed(raw_html)
    problems.extend(auditor.problems)
    visible = " ".join(auditor.visible_text)
    if re.search(r"\[[^\]\n]{1,40}\]", visible):
        problems.append("placeholder entre corchetes sin rellenar")
    claim = _INVENTED_CLAIMS.search(visible)
    if claim:
        problems.append(f"afirmación inventada sobre el negocio: {claim.group(0)!r}")

    photos = brief.media.photos if public_key else ()
    used = [int(n) for n in _PHOTO_TOKEN.findall(raw_html)]
    if any(n < 1 or n > len(photos) for n in used):
        problems.append("marcador de foto fuera de rango")
    if len(used) != len(set(used)):
        problems.append("marcador de foto repetido")
    if photos and not used:
        problems.append("no usó ninguna foto disponible")
    if "{{" in _PHOTO_TOKEN.sub("", raw_html):
        problems.append("marcador desconocido")
    if problems:
        raise InvalidSiteHtml(problems)

    composed = _PHOTO_TOKEN.sub(
        lambda match: _render_figure(photos[int(match.group(1)) - 1], brief.display_name, public_key or ""),
        raw_html,
    )
    composed = re.sub(
        r"(<head(?:\s[^>]*)?>)", lambda match: f"{match.group(1)}{NOINDEX_META}{BASELINE_CSS}", composed, count=1, flags=re.IGNORECASE
    )
    body_end = composed.lower().rfind("</body>")
    return f"{composed[:body_end]}{_render_footer(brief.media)}{composed[body_end:]}"


class SiteBuilder(ABC):
    @abstractmethod
    def build(self, place_id: str, display_name: str, phone_e164: str, gap_analysis: str) -> str:
        ...


class StaticSiteBuilder(SiteBuilder):
    """Plantilla fija del Módulo 7 original — sin LLM ni fotos."""

    def build(self, place_id: str, display_name: str, phone_e164: str, gap_analysis: str) -> str:
        return render_teaser_html(display_name, phone_e164)


class SiteWriter(ABC):
    @abstractmethod
    def write(self, brief: SiteBrief) -> str:
        ...


class GeminiSiteWriter(SiteWriter):
    def __init__(self, model: str = "gemini/gemini-2.5-flash", api_key: str | None = None, completion=None):
        self._model = model
        self._api_key = api_key
        self._completion = completion

    def write(self, brief: SiteBrief) -> str:
        completion = self._completion
        if completion is None:
            import litellm  # import perezoso: solo hace falta corriendo contra Gemini real

            completion = litellm.completion
        response = completion(
            model=self._model,
            api_key=self._api_key,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(brief)},
            ],
            max_tokens=16000,
        )
        return _strip_code_fence(response["choices"][0]["message"]["content"])


class AiSiteBuilder(SiteBuilder):
    """Un error de la API del LLM se propaga (el consumer reintenta con backoff, todavía no se
    deployó nada). Un HTML inválido no es transitorio: se reintenta `max_attempts` veces y si
    sigue mal se degrada a la plantilla fija — el lead nunca se pierde por esto."""

    def __init__(
        self,
        writer: SiteWriter,
        photos_provider: PhotosProvider,
        public_key: str | None,
        max_attempts: int = 2,
    ):
        self._writer = writer
        self._photos_provider = photos_provider
        self._public_key = public_key
        self._max_attempts = max_attempts

    def build(self, place_id: str, display_name: str, phone_e164: str, gap_analysis: str) -> str:
        media = self._photos_provider.fetch(place_id) if self._public_key else PlaceMedia()
        brief = SiteBrief(display_name, phone_e164, gap_analysis, media)
        for attempt in range(1, self._max_attempts + 1):
            try:
                return compose_site(self._writer.write(brief), brief, self._public_key)
            except InvalidSiteHtml as exc:
                logger.warning("sitio inválido para %s (intento %d): %s", place_id, attempt, exc)
        return render_teaser_html(display_name, phone_e164)
