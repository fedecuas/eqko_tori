import dataclasses
import html as html_lib
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from html.parser import HTMLParser

from .design import Theme, pick_theme, theme_head_html
from .photos import PhotosProvider, PlaceMedia, PlacePhoto, photo_media_url
from .template import DISCLAIMER, render_teaser_html

logger = logging.getLogger(__name__)

NOINDEX_META = '<meta name="robots" content="noindex, nofollow">'
MAPS_TOKEN = "{{MAPS_URL}}"

SYSTEM_PROMPT = """Sos un director de arte y desarrollador front-end senior. Vas a generar UN archivo HTML \
completo (una sola página) con el sitio web de un negocio local, con el nivel de una landing de agencia: \
que el dueño lo vea y piense "quiero esto". Respondé SOLO con el HTML (de <!DOCTYPE html> a </html>), sin \
markdown ni explicaciones.

El sistema ya define, y NO podés cambiar: el título, las fuentes de Google, la paleta y los estilos base. Vas a \
recibir los nombres de las variables CSS. Regla dura: todo color sale de var(--...) — sin hex, rgb(), hsl() ni \
nombres de color. Tipografías: font-family: var(--font-display) para títulos y var(--font-body) para el texto.

Clases que el sistema ya provee (usalas; podés complementarlas con tus propios estilos): `.wrap` (contenedor \
centrado con márgenes laterales — envolvé el contenido de TODAS las secciones y del header en un .wrap, así nada \
toca el borde de la pantalla ni se desalinea), `.btn` combinada con `.btn-primary`, `.btn-outline` (sobre fondo \
claro) o `.btn-outline-light` (sobre el hero y fondos oscuros). En móvil el sistema agrega una barra fija inferior \
con WhatsApp y Llamar: no la dupliques.

Estructura (en este orden, mobile-first):
1. Header sticky (position:sticky; top:0; z-index:50; fondo var(--surface) con borde var(--border)): nombre del \
negocio a la izquierda; a la derecha enlaces de ancla (#fotos, #contacto; se ocultan en pantallas chicas) y un botón \
"Llamar" (tel:).
2. Hero de alto impactante (min-height ~80vh): título H1 con el nombre en var(--font-display), tamaño fluido con \
clamp() (ej. clamp(2.6rem, 8vw, 5.5rem)); una línea de apoyo que SOLO contiene la categoría del negocio (si se \
da) y una invitación a contactar (ej. "Restaurante mexicano. Escríbenos o llama."); dos botones grandes: primario \
"Escribir por WhatsApp" y secundario "Llamar". Si hay foto, la primera va de fondo del hero (ver Fotos); si no, fondo var(--hero-bg) con un \
gradiente sutil hecho con var().
3. Franja de 3 tarjetas de acción (enlaces completos, clickeables), cada una con ícono SVG inline, título y una \
línea de apoyo, con este texto exacto: "Escríbenos por WhatsApp" / "Abre el chat"; "Llama directo" / "Marca al \
local"; "Cómo llegar" / "Ábrelo en Google Maps" (esta última solo si se indica ficha).
4. Galería de fotos (id="fotos") con TODAS las fotos restantes: con 3 o más, grilla asimétrica tipo bento (una foto \
grande y varias chicas, con grid-template-areas o spans); bordes redondeados y zoom suave al pasar el mouse. \
Omitila si no quedan fotos.
5. Bloque final de contacto (id="contacto") con fondo var(--hero-bg): título, el teléfono grande y legible, y los \
botones de WhatsApp y llamar.

Diseño (esto es lo que se evalúa):
- Un sistema consistente: escala de espaciado de 8px, radio de 16-24px, sombras con var(--shadow), TODO el \
contenido (hero incluido) alineado al mismo borde izquierdo dentro de `.wrap`, mucho aire vertical entre secciones \
(clamp(56px, 9vw, 112px)).
- Jerarquía tipográfica clara: H1 enorme (más grande que cualquier otro texto), H2 ~clamp(1.8rem, 4vw, 2.75rem), \
cuerpo 17-18px con line-height 1.6, textos de apoyo en var(--muted).
- Botones: usá las clases del sistema (.btn + variante); mínimo 48px de alto ya incluido. cursor:pointer y foco visible \
en todo lo clickeable; las tarjetas clickeables con hover (elevación con var(--shadow) y borde var(--primary)).
- Movimiento CSS sutil (sin JavaScript): entrada del hero con @keyframes (opacity + translateY), hover en tarjetas \
y fotos con transform/box-shadow. Respetá prefers-reduced-motion.
- Íconos: solo SVG inline (viewBox 0 0 24 24, stroke="currentColor", fill="none", stroke-width="2", \
stroke-linecap="round"). Nada de emojis como íconos.
- Responsive real a 375px, 768px y 1280px, sin scroll horizontal. Sin menú hamburguesa: en móvil el header muestra \
solo el nombre y el botón "Llamar".
- Sin JavaScript. Todo el CSS en un único <style> dentro de <head> (después de los estilos del sistema).

Contenido, reglas estrictas (es un negocio real que no pidió esta página):
- Usá SOLO los datos dados. NO inventes horarios, precios, dirección, menú, platillos, reseñas, testimonios, \
premios, años de experiencia, cifras, historia ni nada que no esté en los datos.
- Copy de acción y servicio, no de elogio: verbos (llama, pide, encuentra, escribe). Prohibidos los adjetivos de \
calidad y de origen ("auténtico", "delicioso", "fresco", "casero", "artesanal", "tradicional", "familiar", "de \
siempre", "el mejor", "calidad"), y frases como "nos enorgullece". Nada de secciones de relleno tipo "Aquí irá tu \
menú": si no hay datos para una sección, no la incluyas.
- NO prometas servicios ni productos: nada de entrega, envíos, domicilio, "para llevar", "pasa a recogerlo", \
reservaciones, catering, pedidos ni "ordenar"; tampoco menciones qué venden (tacos, antojitos, sushi, platillos, \
menú): el único dato del giro es la categoría de Google. Lo único que la página ofrece es contactar al local por \
WhatsApp, llamada o ir a su ficha de Maps.
- Español de México, tono cercano. Nada de placeholders entre corchetes.
- WhatsApp: https://wa.me/<solo dígitos>?text=<mensaje corto url-encoded>, ej. ?text=Hola%2C%20quiero%20hacer%20un%20pedido.
- No incluyas <title>, disclaimer, footer, barra de aviso ni meta robots: el sistema los agrega.

Prohibido: <script>, <iframe>, <form>, <img>, <link>, <style> fuera de <head>, url(...) y @import en CSS, atributos \
on*, y enlaces que no sean tel:, https://wa.me/, anclas internas (#) o el marcador de Maps si se indica. En SVG solo \
path, circle, rect, line, polyline, polygon, ellipse y g."""

_FORBIDDEN_TAGS = {
    "script", "iframe", "object", "embed", "form", "input", "textarea", "select", "img", "picture",
    "source", "video", "audio", "canvas", "link", "base", "frame", "frameset", "applet", "math", "title",
}
_SVG_TAGS = {"svg", "path", "circle", "rect", "line", "polyline", "polygon", "ellipse", "g"}
_SVG_ATTRS = {
    "viewbox", "xmlns", "d", "fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "cx", "cy", "r",
    "rx", "ry", "x", "y", "x1", "y1", "x2", "y2", "width", "height", "points", "transform", "fill-rule",
    "clip-rule", "opacity", "class", "aria-hidden", "focusable", "role", "stroke-miterlimit", "fill-opacity",
    "stroke-opacity",
}
_URL_ATTRS = {"src", "srcset", "action", "formaction", "poster", "data", "background", "xlink:href"}
_COLOR_LITERAL = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch|color)\s*\(", re.IGNORECASE
)
_COLOR_NAME_VALUE = re.compile(
    r":[^;{}]*\b(?:white|black|red|green|blue|gray|grey|orange|yellow|purple|pink|brown|navy|teal|gold|silver|"
    r"maroon|crimson|beige|ivory|tan)\b",
    re.IGNORECASE,
)
_INVENTED_CLAIMS = re.compile(
    r"generaci[oó]n|desde\s+(?:el\s+)?\d{4}|\d+\s+a[ñn]os|a[ñn]os de (?:experiencia|tradici)|galardon|premiad|"
    r"\bel mejor\b|\blos mejores\b|n[uú]mero\s*1|#1|enorgullec|de siempre|aut[eé]ntic|tradicion|casero|casera|"
    r"artesanal|familiar|\bfresc[oa]s?\b|delicios|gourmet|exquisit|inigualable|calidad|"
    r"entreg|para llevar|recog[eé]r|domicilio|\benv[ií]os?\b|delivery|reserv|catering|antojit|vis[ií]tanos|"
    r"\bordenar|\btu pedido|\bhaz tu pedido|\bmen[uú]\b",
    re.IGNORECASE,
)
_PHOTO_TOKEN = re.compile(r"\{\{PHOTO_(\d+)\}\}")


class InvalidSiteHtml(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(dict.fromkeys(problems)))
        self.problems = problems


@dataclass(frozen=True)
class SiteBrief:
    display_name: str
    phone_e164: str
    gap_analysis: str
    media: PlaceMedia

    @property
    def theme(self) -> Theme:
        return pick_theme(self.display_name, self.media.primary_type, self.media.category_label)


def _gallery_layout(gallery_photos: int) -> str:
    """La galería se arma con las fotos que quedan tras el hero; el layout depende de cuántas
    sean — un "bento" con solo 2 fotos deja un hueco vacío."""
    if gallery_photos <= 0:
        return "Con estas fotos no hay galería: omití esa sección."
    if gallery_photos == 1:
        return "La galería tiene 1 foto: una sola foto ancha."
    if gallery_photos == 2:
        return "La galería tiene 2 fotos: dos columnas iguales (una debajo de la otra en móvil), sin huecos."
    if gallery_photos == 3:
        return "La galería tiene 3 fotos: una grande a la izquierda y dos apiladas a la derecha, sin huecos."
    return (
        f"La galería tiene {gallery_photos} fotos: grilla bento asimétrica con grid-template-areas, sin celdas vacías "
        "(en móvil, una columna)."
    )


def build_user_prompt(brief: SiteBrief) -> str:
    digits = re.sub(r"\D", "", brief.phone_e164)
    theme = brief.theme
    variables = ", ".join(f"var(--{name.replace('_', '-')})" for name in theme.tokens)
    photo_count = len(brief.media.photos)
    if photo_count:
        tokens = ", ".join(f"{{{{PHOTO_{i}}}}}" for i in range(1, photo_count + 1))
        photos = (
            f"Hay {photo_count} foto(s) reales del negocio: marcadores {tokens}, cada uno una sola vez y escrito tal "
            "cual, como elemento suelto dentro de un contenedor de tu layout. El sistema reemplaza cada marcador por "
            '<figure class="tori-photo"><img ...><figcaption class="tori-attribution">crédito</figcaption></figure>. '
            "No escribas <img>. Estilizá el <img> con `.tori-photo > img` (width:100%; height:100%; object-fit:cover; "
            "border-radius). Usá {{PHOTO_1}} como fondo del hero: contenedor `position:relative; overflow:hidden; "
            "isolation:isolate`; la figura `position:absolute; inset:0; z-index:-2`; una capa `::before` con "
            "background:linear-gradient(...var(--scrim)...) y z-index:-1 para que el texto (color var(--on-hero)) sea "
            "legible; el `figcaption.tori-attribution` de esa foto debe quedar visible abajo a la derecha (position:"
            "absolute; z-index:1; fondo var(--scrim); color var(--on-hero); padding pequeño). En la galería, los "
            "figcaption van debajo de la foto o superpuestos con fondo var(--scrim), siempre legibles. Usá todas las fotos. "
            f"{_gallery_layout(photo_count - 1)} Toda foto de la galería lleva aspect-ratio fijo con object-fit:cover "
            "(las hay verticales o con carteles): nunca dejes que una ocupe más de 70vh."
        )
    else:
        photos = "No hay fotos: no uses <img> ni marcadores; el hero va con fondo var(--hero-bg) y gradiente."
    maps = (
        f"Hay ficha de Google Maps: para la tarjeta \"Cómo llegar\" usá href=\"{MAPS_TOKEN}\" escrito tal cual."
        if brief.media.google_maps_uri
        else "No hay ficha de Google Maps: la tarjeta \"Cómo llegar\" no va; dejá dos tarjetas."
    )
    category = brief.media.category_label
    return (
        f"Negocio: {brief.display_name}\n"
        f"Categoría (dato de Google, solo para el tono visual; no la repitas si no aporta): {category or 'sin dato'}\n"
        f"Teléfono: {brief.phone_e164} (WhatsApp: https://wa.me/{digits})\n"
        f"Variables de color disponibles: {variables}. Tipografías: var(--font-display), var(--font-body).\n"
        f"Tema visual elegido por el sistema: {theme.key} (respetá su personalidad: "
        f"{'oscuro y nocturno' if theme.key == 'bar' else 'cálido y apetitoso'}).\n"
        f"Fotos: {photos}\n"
        f"Maps: {maps}"
    )


def _css_problems(css: str) -> list[str]:
    stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    problems = []
    if re.search(r"url\s*\(|@import|@font-face|expression\s*\(|javascript:", stripped, re.IGNORECASE):
        problems.append("url()/@import/@font-face en CSS")
    if _COLOR_LITERAL.search(stripped) or _COLOR_NAME_VALUE.search(stripped):
        problems.append("color literal en CSS (usar var(--...))")
    return problems


def _href_allowed(value: str) -> bool:
    return value.startswith(("tel:", "https://wa.me/", "#")) or value == MAPS_TOKEN


class _Auditor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.problems: list[str] = []
        self.visible_text: list[str] = []
        self._in_style = False
        self._style_buffer: list[str] = []
        self._svg_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attr_map = {name.lower(): (value or "") for name, value in attrs}
        if tag == "svg":
            self._svg_depth += 1
        if self._svg_depth:
            if tag not in _SVG_TAGS:
                self.problems.append(f"etiqueta no permitida dentro de <svg>: <{tag}>")
            for name, value in attr_map.items():
                if name not in _SVG_ATTRS or re.search(r"url\s*\(|javascript:", value, re.IGNORECASE):
                    self.problems.append(f"atributo SVG no permitido: {name}")
            return
        if tag in _FORBIDDEN_TAGS:
            self.problems.append(f"etiqueta prohibida <{tag}>")
        if tag == "style":
            self._in_style = True
            self._style_buffer = []
        if tag == "meta" and (attr_map.get("name", "").lower() == "robots" or "http-equiv" in attr_map):
            self.problems.append("meta robots/http-equiv no permitido (lo agrega el sistema)")
        for name, value in attr_map.items():
            if name.startswith("on"):
                self.problems.append(f"atributo de evento {name}")
            elif name == "style":
                self.problems.extend(_css_problems(f"x{{{value}}}"))
            elif name == "href" and (tag != "a" or not _href_allowed(value)):
                self.problems.append(f"href no permitido: {value[:60]}")
            elif name in _URL_ATTRS:
                self.problems.append(f"atributo {name} no permitido en <{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if tag == "svg" and self._svg_depth:
            self._svg_depth -= 1
        if tag == "style":
            self._in_style = False
            self.problems.extend(_css_problems("".join(self._style_buffer)))

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self._style_buffer.append(data)
        elif not self._svg_depth:
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


_ICON_ATTRS = (
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true"'
)
_WHATSAPP_ICON = (
    f'<svg {_ICON_ATTRS}><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7'
    'a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z"/></svg>'
)
_PHONE_ICON = (
    f'<svg {_ICON_ATTRS}><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 '
    '2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 '
    '0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/></svg>'
)


def _render_action_bar(phone_e164: str) -> str:
    """Barra fija inferior solo en móvil (el CSS la oculta en desktop): el contacto siempre a
    un toque. La arma el sistema, no el LLM — el diseño ya no depende de que el modelo se
    acuerde de ponerla."""
    digits = re.sub(r"\D", "", phone_e164)
    whatsapp = f"https://wa.me/{digits}?text=Hola%2C%20quisiera%20m%C3%A1s%20informaci%C3%B3n"
    return (
        '<nav class="tori-actionbar" aria-label="Contacto rápido">'
        f'<a class="btn btn-primary" href="{whatsapp}">{_WHATSAPP_ICON}WhatsApp</a>'
        f'<a class="btn btn-outline" href="tel:{html_lib.escape(phone_e164, quote=True)}">{_PHONE_ICON}Llamar</a></nav>'
    )


def _render_preview_bar(display_name: str) -> str:
    name = html_lib.escape(display_name)
    return f'<div class="tori-preview-bar">Vista previa de cómo podría verse el sitio de {name} · No es su sitio oficial</div>'


def _strip_code_fence(content: str) -> str:
    text = content.strip()
    fenced = re.match(r"^```(?:html)?\s*\n(.*)\n```$", text, re.DOTALL | re.IGNORECASE)
    return fenced.group(1).strip() if fenced else text


def compose_site(raw_html: str, brief: SiteBrief, public_key: str | None) -> str:
    """El HTML de Gemini nunca se despliega tal cual: se audita (sin scripts/forms/imágenes
    propias/enlaces externos/colores sueltos) y el sistema inyecta lo que NO se le puede
    delegar al LLM — título, fuentes y paleta, `noindex`, barra de vista previa, disclaimer
    literal, atribución de Google y las etiquetas <img> de las fotos (siempre apuntando en
    vivo a Google, nunca a un archivo nuestro)."""
    problems: list[str] = []
    lowered = raw_html.lower()
    if not re.search(r"<head[\s>]", lowered):
        problems.append("HTML incompleto: falta <head>")
    for marker in ("</head>", "<body", "</body>", "</html>"):
        if marker not in lowered:
            problems.append(f"HTML incompleto: falta {marker}")

    # <title> lo pone el sistema: se descarta el del modelo antes de auditar.
    without_title = re.sub(r"<title[^>]*>.*?</title>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
    auditor = _Auditor()
    auditor.feed(without_title)
    problems.extend(auditor.problems)
    visible = " ".join(auditor.visible_text)
    if re.search(r"\[[^\]\n]{1,40}\]", visible):
        problems.append("placeholder entre corchetes sin rellenar")
    claim = _INVENTED_CLAIMS.search(visible)
    if claim:
        problems.append(f"afirmación inventada sobre el negocio: {claim.group(0)!r}")

    photos = brief.media.photos if public_key else ()
    used = [int(n) for n in _PHOTO_TOKEN.findall(without_title)]
    if any(n < 1 or n > len(photos) for n in used):
        problems.append("marcador de foto fuera de rango")
    if len(used) != len(set(used)):
        problems.append("marcador de foto repetido")
    if photos and not used:
        problems.append("no usó ninguna foto disponible")
    maps_uri = _https(brief.media.google_maps_uri)
    if MAPS_TOKEN in without_title and not maps_uri:
        problems.append("usó el marcador de Maps sin ficha disponible")
    if "{{" in _PHOTO_TOKEN.sub("", without_title).replace(MAPS_TOKEN, ""):
        problems.append("marcador desconocido")
    if problems:
        raise InvalidSiteHtml(problems)

    composed = _PHOTO_TOKEN.sub(
        lambda match: _render_figure(photos[int(match.group(1)) - 1], brief.display_name, public_key or ""),
        without_title,
    )
    if maps_uri:
        composed = composed.replace(MAPS_TOKEN, html_lib.escape(maps_uri, quote=True))
    # charset primero: tiene que caer en los primeros 1024 bytes del documento.
    head_extra = (
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        f"{NOINDEX_META}<title>{html_lib.escape(brief.display_name)}</title>{theme_head_html(brief.theme)}"
    )
    composed = re.sub(
        r"(<head(?:\s[^>]*)?>)", lambda match: f"{match.group(1)}{head_extra}", composed, count=1, flags=re.IGNORECASE
    )
    composed = re.sub(
        r"(<body(?:\s[^>]*)?>)",
        lambda match: f"{match.group(1)}{_render_preview_bar(brief.display_name)}",
        composed,
        count=1,
        flags=re.IGNORECASE,
    )
    body_end = composed.lower().rfind("</body>")
    tail = f"{_render_footer(brief.media)}{_render_action_bar(brief.phone_e164)}"
    return f"{composed[:body_end]}{tail}{composed[body_end:]}"


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
    def __init__(self, model: str = "gemini/gemini-3.1-pro-preview", api_key: str | None = None, completion=None):
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
            max_tokens=32000,
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
        max_attempts: int = 3,
    ):
        self._writer = writer
        self._photos_provider = photos_provider
        self._public_key = public_key
        self._max_attempts = max_attempts

    def build(self, place_id: str, display_name: str, phone_e164: str, gap_analysis: str) -> str:
        media = self._photos_provider.fetch(place_id)
        if not self._public_key:
            media = dataclasses.replace(media, photos=())  # sin key pública no hay URL válida de foto
        brief = SiteBrief(display_name, phone_e164, gap_analysis, media)
        for attempt in range(1, self._max_attempts + 1):
            try:
                return compose_site(self._writer.write(brief), brief, self._public_key)
            except InvalidSiteHtml as exc:
                logger.warning("sitio inválido para %s (intento %d): %s", place_id, attempt, exc)
        return render_teaser_html(display_name, phone_e164)
