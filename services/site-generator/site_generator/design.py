"""Sistema de diseño de los sitios generados. La paleta y las tipografías las fija el SISTEMA,
no el LLM: Gemini solo compone el layout usando `var(--token)`. Así el contraste queda
garantizado por construcción (ver tests/test_design.py, que calcula cada par) en vez de
depender de que el modelo elija bien los colores."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    key: str
    tokens: dict[str, str]
    font_display: str
    font_body: str
    fonts_url: str


_COMMON = {"scrim": "rgba(10, 10, 10, 0.62)", "shadow": "0 10px 30px rgba(0, 0, 0, 0.14)"}


def _theme(key: str, font_display: str, font_body: str, fonts_url: str, **tokens: str) -> Theme:
    return Theme(key, {**_COMMON, **tokens}, font_display, font_body, fonts_url)


THEMES: dict[str, Theme] = {
    "mexicano": _theme(
        "mexicano", "'Bebas Neue', Impact, sans-serif", "'Inter', system-ui, sans-serif",
        "https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@400;500;600;700&display=swap",
        bg="#FFF7ED", surface="#FFFFFF", ink="#2A1408", muted="#6B4A34", primary="#C2410C",
        on_primary="#FFFFFF", primary_dark="#9A3412", hero_bg="#2A1408", on_hero="#FFF7ED", border="#F1DEC9",
    ),
    "oriental": _theme(
        "oriental", "'Playfair Display', Georgia, serif", "'Inter', system-ui, sans-serif",
        "https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Inter:wght@400;500;600;700&display=swap",
        bg="#F8F6F1", surface="#FFFFFF", ink="#16181D", muted="#545B66", primary="#B91C1C",
        on_primary="#FFFFFF", primary_dark="#991B1B", hero_bg="#16181D", on_hero="#F8F6F1", border="#E7E2D8",
    ),
    "cafe": _theme(
        "cafe", "'Fraunces', Georgia, serif", "'DM Sans', system-ui, sans-serif",
        "https://fonts.googleapis.com/css2?family=Fraunces:wght@600;700&family=DM+Sans:wght@400;500;700&display=swap",
        bg="#FBF7F2", surface="#FFFFFF", ink="#2B2119", muted="#6A5747", primary="#7C4A2D",
        on_primary="#FFFFFF", primary_dark="#5E3720", hero_bg="#2B2119", on_hero="#FBF7F2", border="#EBDFD2",
    ),
    "bar": _theme(
        "bar", "'Oswald', Impact, sans-serif", "'Inter', system-ui, sans-serif",
        "https://fonts.googleapis.com/css2?family=Oswald:wght@500;600&family=Inter:wght@400;500;600;700&display=swap",
        bg="#14110F", surface="#201B18", ink="#F6EFE6", muted="#B8AA9A", primary="#F59E0B",
        on_primary="#1A1200", primary_dark="#D98A00", hero_bg="#0C0A09", on_hero="#F6EFE6", border="#33291F",
    ),
    "general": _theme(
        "general", "'DM Serif Display', Georgia, serif", "'DM Sans', system-ui, sans-serif",
        "https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;700&display=swap",
        bg="#FAF9F6", surface="#FFFFFF", ink="#1C1917", muted="#57534E", primary="#0F766E",
        on_primary="#FFFFFF", primary_dark="#115E59", hero_bg="#12302D", on_hero="#F0FDFA", border="#E7E5E4",
    ),
}

_KEYWORDS = (
    ("oriental", ("sushi", "ramen", "japan", "asian", "asiat", "thai", "chin", "korea", "wok", "roll")),
    ("cafe", ("cafe", "café", "coffee", "bakery", "panader", "pasteler", "dessert", "postre", "ice_cream", "helader")),
    ("bar", ("bar$", "pub$", "cantina", "cerve", "brew", "night_club", "antro", "cocteler")),
    ("mexicano", ("taco", "taquer", "mexican", "mexicana", "birria", "antojit", "clamato", "snack", "torta", "pozole", "carnita")),
)


def pick_theme(display_name: str, primary_type: str | None = None, category_label: str | None = None) -> Theme:
    """Categoría de Places primero (más confiable que el nombre), luego el nombre."""
    for haystack in (f"{primary_type or ''} {category_label or ''}".lower(), display_name.lower()):
        if not haystack.strip():
            continue
        for key, words in _KEYWORDS:
            if any(_matches(word, haystack) for word in words):
                return THEMES[key]
    return THEMES["general"]


def _matches(word: str, haystack: str) -> bool:
    """`word$` = palabra completa (ej. "bar" no debe matchear "barbacoa"); sin `$` = prefijo."""
    letters = "a-záéíóúñ"
    whole = word.endswith("$")
    pattern = rf"(?<![{letters}]){re.escape(word.rstrip('$'))}" + (rf"(?![{letters}])" if whole else "")
    return bool(re.search(pattern, haystack))


def _css_name(token: str) -> str:
    return token.replace("_", "-")


def theme_head_html(theme: Theme) -> str:
    """Fuentes (Google Fonts, inyectadas por el sistema — el LLM no puede escribir <link>) y
    variables CSS del tema + estilos base que garantizan una página legible aunque el CSS
    del modelo falle."""
    variables = ";".join(f"--{_css_name(name)}:{value}" for name, value in theme.tokens.items())
    css = (
        f":root{{{variables};--font-display:{theme.font_display};--font-body:{theme.font_body}}}"
        "*,*::before,*::after{box-sizing:border-box}"
        "html{scroll-behavior:smooth}"
        "body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font-body);line-height:1.6;"
        "-webkit-font-smoothing:antialiased}"
        "img{max-width:100%;height:auto}a{color:inherit}"
        ":focus-visible{outline:3px solid var(--primary);outline-offset:3px}"
        ".wrap{width:min(1120px,calc(100% - 40px));margin-inline:auto}"
        ".btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:48px;padding:0 24px;"
        "border-radius:999px;border:2px solid transparent;font:600 1rem/1 var(--font-body);text-decoration:none;"
        "cursor:pointer;transition:background-color .2s,color .2s,border-color .2s}"
        ".btn svg{width:20px;height:20px;flex:none}"
        ".btn-primary{background:var(--primary);color:var(--on-primary)}.btn-primary:hover{background:var(--primary-dark)}"
        ".btn-outline{border-color:var(--ink);color:var(--ink)}"
        ".btn-outline:hover{background:var(--ink);color:var(--bg)}"
        ".btn-outline-light{border-color:var(--on-hero);color:var(--on-hero)}"
        ".btn-outline-light:hover{background:var(--on-hero);color:var(--hero-bg)}"
        ".tori-actionbar{display:none}"
        "@media (max-width:767px){body{padding-bottom:80px}.tori-actionbar{display:flex;gap:12px;position:fixed;"
        "left:0;right:0;bottom:0;z-index:100;padding:12px 16px calc(12px + env(safe-area-inset-bottom));"
        "background:var(--surface);border-top:1px solid var(--border);box-shadow:0 -6px 20px rgba(0,0,0,.1)}"
        ".tori-actionbar .btn{flex:1;padding:0 12px}}"
        ".tori-photo{margin:0;position:relative}.tori-photo img{display:block;max-width:100%}"
        ".tori-attribution{font-size:12px;line-height:1.4;color:var(--muted)}.tori-attribution a{color:inherit}"
        ".tori-preview-bar{background:var(--hero-bg);color:var(--on-hero);font-size:13px;text-align:center;padding:8px 16px}"
        ".tori-footer{display:block;position:static;background:var(--surface);color:var(--muted);font-size:13px;"
        "border-top:1px solid var(--border);padding:24px 16px;text-align:center}"
        ".tori-footer p{max-width:720px;margin:6px auto}.tori-footer a{color:inherit}"
        "@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;"
        "transition:none!important;scroll-behavior:auto!important}}"
    )
    return (
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        f'<link rel="stylesheet" href="{theme.fonts_url}">'
        f"<style>{css}</style>"
    )


def contrast_ratio(foreground: str, background: str) -> float:
    def luminance(hex_color: str) -> float:
        channels = [int(hex_color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)
