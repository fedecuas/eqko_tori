import hmac

from fastapi import Depends, Header, HTTPException, status

from .config import Settings
from .dependencies import get_settings


def require_internal_api_key(
    x_internal_api_key: str = Header(default=""),
    settings: Settings = Depends(get_settings),
) -> None:
    """Mismo patrón que services/extractor: aprobar/rechazar leads es una acción con efecto
    real (dispara el dispatch), no puede quedar público."""
    if not hmac.compare_digest(x_internal_api_key, settings.tori_internal_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing X-Internal-Api-Key")
