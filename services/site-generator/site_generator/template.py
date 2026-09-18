import html as html_lib

DISCLAIMER = (
    "Vista previa automática generada a partir de información pública de tu negocio en "
    "Google Maps — no es tu sitio oficial. Si querés que la bajemos, respondé por el mismo "
    "medio por el que te contactamos."
)
"""Texto exacto acordado en el documento de validación del Módulo 7 (CLAUDE.md sección 9,
2026-09-18): la baja se gestiona por el mismo canal de contacto, no una dirección separada.
No cambiar sin volver a pasar por esa validación — es la mitigación de la Capa B
(consentimiento del negocio), no un detalle de copy."""


def render_teaser_html(display_name: str, phone_e164: str, rating_note: str | None = None) -> str:
    """Sin fotos ni texto de reviews de Google Places (Capa A de la validación) — solo datos
    factuales del negocio (nombre, teléfono) más, si se pasa, una CITA con link a la ficha
    real de Google (nunca el texto de una review). `noindex, nofollow` siempre presente, no
    es opcional."""
    name = html_lib.escape(display_name)
    phone = html_lib.escape(phone_e164)
    rating_block = f'<p class="rating">{html_lib.escape(rating_note)}</p>' if rating_note else ""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{name}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; margin: 0; padding: 0; color: #1a1a1a; }}
  header {{ background: #0E1C2D; color: #fff; padding: 48px 24px; text-align: center; }}
  header h1 {{ margin: 0 0 8px; font-size: 28px; }}
  main {{ max-width: 640px; margin: 0 auto; padding: 32px 24px; }}
  .rating {{ color: #555; }}
  .contact {{ background: #f4f4f4; border-radius: 8px; padding: 16px; margin-top: 24px; }}
  .disclaimer {{ font-size: 13px; color: #777; margin-top: 40px; border-top: 1px solid #eee; padding-top: 16px; }}
</style>
</head>
<body>
<header>
  <h1>{name}</h1>
  <p>Presencia digital propia, en minutos.</p>
</header>
<main>
  {rating_block}
  <p>Notamos que {name} todavía no tiene un sitio propio. Esta es una vista previa de cómo
  podría verse — simple, rápida, con tu info de contacto a mano.</p>
  <div class="contact">
    <strong>Contacto:</strong> {phone}
  </div>
  <p class="disclaimer">{html_lib.escape(DISCLAIMER)}</p>
</main>
</body>
</html>
"""
