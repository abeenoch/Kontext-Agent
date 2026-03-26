import os
import sys
import types
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure the repo root is importable as a package (app/ lives here).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Ensure tests run against a lightweight local SQLite database and test-safe env.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

# Disable Chroma telemetry during tests to avoid background-thread crashes on exit.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_ENABLED", "False")

# Replace chromadb with a minimal in-memory stub for smoke tests.
if "chromadb" not in sys.modules:
    chromadb_stub = types.ModuleType("chromadb")

    class _DummyCollection:
        def __init__(self):
            self._docs = []

        def upsert(self, ids=None, documents=None, embeddings=None, metadatas=None):
            if documents:
                self._docs.extend(documents)

        def count(self):
            return len(self._docs)

        def query(self, query_embeddings=None, n_results=3):
            return {"documents": [self._docs[:n_results]]}

    class _DummyClient:
        def __init__(self, path=None):
            self._collections = {}

        def get_or_create_collection(self, name):
            if name not in self._collections:
                self._collections[name] = _DummyCollection()
            return self._collections[name]

        def delete_collection(self, name):
            self._collections.pop(name, None)

    chromadb_stub.Collection = _DummyCollection
    chromadb_stub.PersistentClient = _DummyClient
    sys.modules["chromadb"] = chromadb_stub

# Stub rag_pipeline to avoid importing heavy ML stacks in smoke tests.
if "app.services.rag_pipeline" not in sys.modules:
    rag_stub = types.ModuleType("app.services.rag_pipeline")

    async def _stub_ingest_file(user_id, tab_id, filename, content):
        return 1

    async def _stub_retrieve_docs(user_id, tab_id, query, n_results=3):
        return []

    async def _stub_clear_user_docs(user_id, tab_id=None):
        return None

    def _stub_list_user_docs(user_id, tab_id, limit=20):
        return []

    rag_stub.ingest_file = _stub_ingest_file
    rag_stub.retrieve_docs = _stub_retrieve_docs
    rag_stub.clear_user_docs = _stub_clear_user_docs
    rag_stub.list_user_docs = _stub_list_user_docs
    sys.modules["app.services.rag_pipeline"] = rag_stub

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(client):
    email = f"smoke_{uuid.uuid4().hex[:10]}@example.com"
    password = "smoketest123"

    signup = client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": password,
            "display_name": "Smoke User",
        },
    )
    assert signup.status_code == 201, signup.text

    token = signup.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
