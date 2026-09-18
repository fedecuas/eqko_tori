from agent_worker.rag import Embedder, MessageExample, PostgresMessageExamplesRepository

from .fakes import StubMessageExamplesRepository


def test_stub_repository_returns_up_to_limit():
    repo = StubMessageExamplesRepository(
        [
            MessageExample(tenant_id="alba", message_text="msg1"),
            MessageExample(tenant_id="alba", message_text="msg2"),
            MessageExample(tenant_id="alba", message_text="msg3"),
        ]
    )

    results = repo.find_similar("alba", "taquerias en Guadalajara", limit=2)

    assert len(results) == 2
    assert repo.calls == [{"tenant_id": "alba", "query_text": "taquerias en Guadalajara", "limit": 2}]


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params):
        self.executed = (query, params)

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self, rows):
        self._rows = rows
        self.cursor_obj: _FakeCursor | None = None

    def cursor(self):
        self.cursor_obj = _FakeCursor(self._rows)
        return self.cursor_obj


class _FixedEmbedder(Embedder):
    def embed(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


def test_postgres_repository_maps_rows_and_uses_the_embedding_in_the_query():
    rows = [("Mensaje exitoso 1", "restaurante", 0.92), ("Mensaje exitoso 2", None, 0.81)]
    connection = _FakeConnection(rows)
    repo = PostgresMessageExamplesRepository(connection, _FixedEmbedder())

    results = repo.find_similar("alba", "taquería en Guadalajara", limit=2)

    assert [r.message_text for r in results] == ["Mensaje exitoso 1", "Mensaje exitoso 2"]
    assert results[0].similarity == 0.92
    assert results[1].business_category is None

    query, params = connection.cursor_obj.executed
    assert "message_examples" in query
    assert "embedding <=> %s::vector" in query
    # Literal de texto de pgvector, no el list[float] crudo -- ver comentario en rag.py sobre
    # por qué psycopg necesita el cast ::vector (probado contra un Postgres+pgvector real).
    assert params == ("[0.1,0.2,0.3]", "alba", "[0.1,0.2,0.3]", 2)
