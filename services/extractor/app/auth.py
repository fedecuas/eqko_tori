import hmac

from fastapi import Depends, Header, HTTPException, status

from .config import Settings
from .dependencies import get_settings


def require_internal_api_key(
    x_internal_api_key: str = Header(default=""),
    settings: Settings = Depends(get_settings),
) -> None:
    """POST /runs no puede quedar público — solo el dashboard y Jarvis deberían poder
    dispararlo (mismo patrón que x-jarvis-internal-key en Jarvis). Comparación en tiempo
    constante para no filtrar la key por timing."""
    if not hmac.compare_digest(x_internal_api_key, settings.tori_internal_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing X-Internal-Api-Key")
