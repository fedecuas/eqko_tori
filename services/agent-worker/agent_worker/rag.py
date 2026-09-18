from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class MessageExample:
    tenant_id: str
    message_text: str
    business_category: str | None = None
    similarity: float | None = None


class Embedder(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...


class MessageExamplesRepository(ABC):
    """RAG sobre mensajes exitosos previos y tono de marca por tenant (CLAUDE.md sección 2,
    Módulo 4)."""

    @abstractmethod
    def find_similar(self, tenant_id: str, query_text: str, limit: int = 3) -> list[MessageExample]:
        ...


def _to_pgvector_literal(embedding: list[float]) -> str:
    # psycopg no sabe adaptar un list[float] de Python al tipo `vector` de pgvector por su
    # cuenta -- manda un array literal de Postgres y el operador <=> no existe para ese tipo
    # (UndefinedFunction: "vector <=> double precision[]", confirmado corriendo esto contra
    # un Postgres+pgvector real). El literal de texto "[0.1,0.2,...]" + cast ::vector en la
    # query sí funciona, sin agregar la dependencia del paquete `pgvector` solo por esto.
    return "[" + ",".join(str(value) for value in embedding) + "]"


class PostgresMessageExamplesRepository(MessageExamplesRepository):
    """Implementación real con pgvector, sobre la tabla `message_examples` de
    packages/database (ver su README para el schema, ya aplicado y probado contra un
    Postgres+pgvector local vía Docker).

    `connection` es cualquier objeto DBAPI-2 (ej. psycopg) con `.cursor()`; no se importa
    psycopg acá para no forzar la dependencia en quien no vaya a correr esto (ver pyproject
    `[postgres]`)."""

    def __init__(self, connection: Any, embedder: Embedder):
        self._connection = connection
        self._embedder = embedder

    def find_similar(self, tenant_id: str, query_text: str, limit: int = 3) -> list[MessageExample]:
        query_embedding = _to_pgvector_literal(self._embedder.embed(query_text))
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT message_text, business_category, 1 - (embedding <=> %s::vector) AS similarity
                FROM message_examples
                WHERE tenant_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_embedding, tenant_id, query_embedding, limit),
            )
            rows = cursor.fetchall()

        return [
            MessageExample(
                tenant_id=tenant_id,
                message_text=row[0],
                business_category=row[1],
                similarity=row[2],
            )
            for row in rows
        ]


class LiteLLMEmbedder(Embedder):
    """`api_key` explícito por el mismo motivo que en `LiteLLMMessageDrafter` (brain.py):
    los `.env` de este monorepo no propagan a `os.environ`, litellm nunca vería la key si
    dependiera de leerla del entorno.

    `dimensions` trunca la salida (Matryoshka) al ancho que espera el schema de
    `packages/database` (`VECTOR(768)`). Sin esto, `gemini-embedding-001` devuelve 3072
    dimensiones por default — que ni siquiera indexa en pgvector, `ivfflat`/`hnsw` rechazan
    columnas de más de 2000 dimensiones (confirmado contra un Postgres+pgvector real). El
    parámetro es `dimensions` (el estándar cross-provider de litellm), no
    `output_dimensionality` (el nombre nativo de la API de Gemini) — litellm ignora este
    último en silencio si se lo pasa directo, sin truncar nada."""

    def __init__(
        self,
        model: str = "gemini/gemini-embedding-001",
        api_key: str | None = None,
        dimensions: int = 768,
    ):
        self._model = model
        self._api_key = api_key
        self._dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        import litellm  # import perezoso: no forzar litellm en quien solo usa el stub en tests

        response = litellm.embedding(
            model=self._model, input=[text], api_key=self._api_key, dimensions=self._dimensions
        )
        return response["data"][0]["embedding"]
