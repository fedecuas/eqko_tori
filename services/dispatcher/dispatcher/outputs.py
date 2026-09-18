from abc import ABC, abstractmethod

import httpx
from tori_shared_types import LeadApprovedEvent

# Mismo orden de columnas para Airtable (nombres de campo) y Sheets (columnas A-G).
FIELD_NAMES = ["place_id", "display_name", "phone_e164", "message_text", "gap_analysis", "tenant_id", "landing_url"]
LAST_COLUMN = chr(ord("A") + len(FIELD_NAMES) - 1)


class LeadOutput(ABC):
    """CLAUDE.md sección 3: "Google Sheets API / Airtable API / CRM del cliente". `name` se usa
    en la key del rate limiter y en `LeadDispatchedEvent.output` — ver naming
    `dispatch:<output>:<tenant_id>` en CLAUDE.md sección 5."""

    name: str

    @abstractmethod
    def upsert(self, event: LeadApprovedEvent) -> None:
        """Debe ser seguro de llamar más de una vez para el mismo place_id (redelivery del
        consumer group) — nunca debe crear una fila duplicada."""
        ...


def _row_values(event: LeadApprovedEvent) -> list[str]:
    return [
        event.place_id,
        event.display_name,
        event.phone_e164,
        event.message_text,
        event.gap_analysis,
        event.tenant_id,
        event.landing_url or "",
    ]


class AirtableOutput(LeadOutput):
    """⚠️ Sin probar contra la API real — requiere AIRTABLE_ACCESS_TOKEN (TORI-CREDENTIALS.md,
    scopeado solo a la base del tenant). Usa el `performUpsert` nativo de Airtable
    (fieldsToMergeOn=["place_id"]) — no hace falta buscar la fila nosotros."""

    name = "airtable"
    BASE_URL = "https://api.airtable.com/v0"

    def __init__(self, access_token: str, base_id: str, table_name: str, client: httpx.Client | None = None):
        self._access_token = access_token
        self._base_id = base_id
        self._table_name = table_name
        self._client = client or httpx.Client(timeout=15.0)

    def upsert(self, event: LeadApprovedEvent) -> None:
        fields = dict(zip(FIELD_NAMES, _row_values(event)))
        response = self._client.patch(
            f"{self.BASE_URL}/{self._base_id}/{self._table_name}",
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            },
            json={
                "performUpsert": {"fieldsToMergeOn": ["place_id"]},
                "records": [{"fields": fields}],
            },
        )
        response.raise_for_status()


class GoogleSheetsOutput(LeadOutput):
    """⚠️ Sin probar contra la API real — requiere GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON
    (TORI-CREDENTIALS.md). Sheets no tiene upsert nativo: busca la fila por `place_id` en la
    columna A y actualiza, o agrega una fila nueva si no existe."""

    name = "sheets"
    BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets"

    def __init__(self, access_token: str, spreadsheet_id: str, sheet_name: str = "Leads", client: httpx.Client | None = None):
        self._access_token = access_token
        self._spreadsheet_id = spreadsheet_id
        self._sheet_name = sheet_name
        self._client = client or httpx.Client(timeout=15.0)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token}"}

    def _find_row_number(self, place_id: str) -> int | None:
        response = self._client.get(
            f"{self.BASE_URL}/{self._spreadsheet_id}/values/{self._sheet_name}!A:A",
            headers=self._headers(),
        )
        response.raise_for_status()
        for index, row in enumerate(response.json().get("values", []), start=1):
            if row and row[0] == place_id:
                return index
        return None

    def upsert(self, event: LeadApprovedEvent) -> None:
        row_values = _row_values(event)
        row_number = self._find_row_number(event.place_id)

        if row_number is not None:
            response = self._client.put(
                f"{self.BASE_URL}/{self._spreadsheet_id}/values/{self._sheet_name}!A{row_number}:{LAST_COLUMN}{row_number}",
                params={"valueInputOption": "RAW"},
                headers=self._headers(),
                json={"values": [row_values]},
            )
        else:
            response = self._client.post(
                f"{self.BASE_URL}/{self._spreadsheet_id}/values/{self._sheet_name}!A:{LAST_COLUMN}:append",
                params={"valueInputOption": "RAW"},
                headers=self._headers(),
                json={"values": [row_values]},
            )
        response.raise_for_status()


class OutputRouter(ABC):
    @abstractmethod
    def get_output(self, tenant_id: str) -> LeadOutput:
        ...


class StaticOutputRouter(OutputRouter):
    """Sin `packages/database` todavía no hay dónde guardar "qué output usa cada tenant" de
    forma dinámica — se configura acá mismo al construir el proceso (ver main.py). Un tenant
    sin output configurado levanta ValueError, que el handler deja propagar: es un problema de
    configuración real, no un dato de negocio, así que debe terminar en la DLQ para que alguien
    lo revise, no descartarse en silencio."""

    def __init__(self, outputs_by_tenant: dict[str, LeadOutput]):
        self._outputs_by_tenant = outputs_by_tenant

    def get_output(self, tenant_id: str) -> LeadOutput:
        try:
            return self._outputs_by_tenant[tenant_id]
        except KeyError:
            raise ValueError(f"no hay output configurado para tenant_id={tenant_id!r}") from None
