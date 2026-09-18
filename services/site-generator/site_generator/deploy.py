import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx


@dataclass
class DeployResult:
    url: str
    deployment_id: str


class SiteDeployer(ABC):
    @abstractmethod
    def deploy(self, html: str, slug: str) -> DeployResult:
        ...

    @abstractmethod
    def delete(self, deployment_id: str) -> None:
        ...


def slug_for(place_id: str) -> str:
    # Hash, no el nombre del negocio — parte de la mitigación de exposición (Capa B): el
    # link no debe ser adivinable a partir del nombre del negocio.
    return hashlib.sha256(place_id.encode()).hexdigest()[:16]


class VercelDeployer(SiteDeployer):
    """Deploy de un único archivo estático (`index.html`), sin build step — no hace falta más
    para un teaser.

    `project_name` es un proyecto de Vercel que **ya tiene que existir** — cada deploy se
    manda a `project_name` (no crea uno nuevo). Probado contra la API real: un token de
    Vercel scopeado a un team normalmente NO tiene permiso para crear proyectos nuevos
    (`403 "You don't have permission to create a project"`, confirmado 2026-09-18), aunque sí
    puede deployar de sobra en uno que ya existe. El diseño original mandaba un `name` único
    por lead (`f"{project_name}-{slug}"`), que Vercel interpretaba como "crear un proyecto
    nuevo" — de ahí el 403. Cada deployment igual recibe su propia URL única generada por
    Vercel (el hash en el subdominio, ej. `eqkotori-mkf012n2h-....vercel.app`), no hace falta
    un proyecto por lead para eso."""

    BASE_URL = "https://api.vercel.com"

    def __init__(self, token: str, project_name: str, team_id: str | None = None, client: httpx.Client | None = None):
        self._token = token
        self._project_name = project_name
        self._team_id = team_id
        self._client = client or httpx.Client(timeout=30.0)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def _params(self) -> dict:
        return {"teamId": self._team_id} if self._team_id else {}

    def deploy(self, html: str, slug: str) -> DeployResult:
        response = self._client.post(
            f"{self.BASE_URL}/v13/deployments",
            headers=self._headers(),
            params=self._params(),
            json={
                "name": self._project_name,
                "project": self._project_name,
                "target": "production",
                "files": [{"file": "index.html", "data": html}],
                "projectSettings": {"framework": None},
                # Sin efecto funcional -- queda en el dashboard de Vercel para poder
                # rastrear a mano qué deployment corresponde a qué place_id si hace falta.
                "meta": {"tori_place_slug": slug},
            },
        )
        response.raise_for_status()
        body = response.json()
        url = body["url"]
        if not re.match(r"^https?://", url):
            url = f"https://{url}"
        return DeployResult(url=url, deployment_id=body["id"])

    def delete(self, deployment_id: str) -> None:
        response = self._client.delete(
            f"{self.BASE_URL}/v13/deployments/{deployment_id}",
            headers=self._headers(),
            params=self._params(),
        )
        if response.status_code == 404:
            return  # ya no existe -- borrarlo de nuevo no es un error
        response.raise_for_status()
