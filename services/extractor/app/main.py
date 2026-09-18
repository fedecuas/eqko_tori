import uuid

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from idempotency import IdempotencyStore
from tori_shared_types import RunRequest

from .auth import require_internal_api_key
from .dependencies import get_idempotency_store, get_places_provider, get_publisher, get_run_store
from .pipeline import run_extraction
from .places_client import PlacesProvider
from .run_store import RunStore
from .streams import StreamsPublisher

app = FastAPI(title="TORI Extractor", version="0.1.0")


@app.post("/runs", status_code=202, dependencies=[Depends(require_internal_api_key)])
def create_run(
    request: RunRequest,
    background_tasks: BackgroundTasks,
    places_provider: PlacesProvider = Depends(get_places_provider),
    idempotency_store: IdempotencyStore = Depends(get_idempotency_store),
    publisher: StreamsPublisher = Depends(get_publisher),
    run_store: RunStore = Depends(get_run_store),
) -> dict:
    run_id = str(uuid.uuid4())
    run_store.create(run_id, request.tenant_id, request.query)

    # Responde ya — la extracción corre en background, el Trigger Layer nunca espera
    # a que termine (CLAUDE.md sección 1, riesgo "Procesamiento síncrono").
    background_tasks.add_task(
        run_extraction, run_id, request, places_provider, idempotency_store, publisher, run_store
    )

    return {"run_id": run_id, "status": "queued"}


@app.get("/runs/{run_id}", dependencies=[Depends(require_internal_api_key)])
def get_run(run_id: str, run_store: RunStore = Depends(get_run_store)) -> dict:
    run = run_store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
