import logging
from datetime import datetime, timezone

from idempotency import IdempotencyStore
from tori_shared_types import PlaceExtractedEvent, RunRequest

from .places_client import PlacesProvider
from .run_store import RunStore
from .streams import StreamsPublisher

logger = logging.getLogger(__name__)


def run_extraction(
    run_id: str,
    request: RunRequest,
    places_provider: PlacesProvider,
    idempotency_store: IdempotencyStore,
    publisher: StreamsPublisher,
    run_store: RunStore,
) -> None:
    """Se corre en background (FastAPI BackgroundTasks) — POST /runs ya respondió antes de
    que esto arranque. No hace el filtro website/phone: eso es responsabilidad del
    Agent Stage (services/agent-worker, Módulo 3-4), acá solo se extrae y se publica."""
    run_store.set_running(run_id)
    found = published = duplicates = 0

    try:
        places = places_provider.search(
            query=request.query,
            latitude=request.latitude,
            longitude=request.longitude,
            radius_meters=request.radius_meters,
            max_results=request.max_results,
        )
        found = len(places)

        for place in places:
            event = PlaceExtractedEvent(
                run_id=run_id,
                tenant_id=request.tenant_id,
                place_id=place.place_id,
                display_name=place.display_name,
                formatted_address=place.formatted_address,
                website_uri=place.website_uri,
                international_phone_number=place.international_phone_number,
                extracted_at=datetime.now(timezone.utc),
            )

            if not idempotency_store.mark_if_new(event.idempotency_key()):
                duplicates += 1
                continue

            publisher.publish_place_extracted(event)
            published += 1

        run_store.set_completed(run_id, found=found, published=published, duplicates=duplicates)
    except Exception as exc:  # el run queda marcado failed, no tumba el worker
        logger.exception("run %s failed", run_id)
        run_store.set_failed(run_id, error=str(exc))
