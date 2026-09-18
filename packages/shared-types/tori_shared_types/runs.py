from enum import Enum

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunRequest(BaseModel):
    """Input de POST /runs en services/extractor."""

    tenant_id: str = Field(min_length=1)
    query: str = Field(min_length=1, description="Texto de búsqueda, ej. 'restaurantes en Guadalajara'")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_meters: int | None = Field(default=None, ge=1, le=50_000)
    max_results: int = Field(default=20, ge=1, le=60)
