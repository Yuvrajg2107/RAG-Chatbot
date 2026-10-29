"""Cloud storage contracts without network access or provider credentials."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from vercel.blob import BlobError, BlobNotFoundError, BlobPreconditionFailedError

from app import cloud_store, rag, store
from app.main import RECENT, app

OWNER = "a" * 64
OTHER = "b" * 64


class FakeBlob:
    def __init__(self):
        self.objects = {}
        self.fail_cleanup = False

    def put_blob(self, pathname, body, **kwargs):
        assert kwargs["access"] == "private"
        if pathname in self.objects and not kwargs.get("allow_overwrite"):
            raise BlobError("Already exists", status_code=409)
        body = bytes(body)
        metadata = SimpleNamespace(
            pathname=pathname, etag=hashlib.sha256(body).hexdigest(), uploaded_at=datetime.now(UTC)
        )
        self.objects[pathname] = (body, metadata)
        return metadata

    def get_blob(self, pathname, **kwargs):
        assert kwargs["access"] == "private"
        if pathname not in self.objects:
            raise BlobNotFoundError()
        return SimpleNamespace(body=self.objects[pathname][0])

    def head_blob(self, pathname):
        if pathname not in self.objects:
            raise BlobNotFoundError()
        return self.objects[pathname][1]

    def query_blobs(self, *, prefix):
        return [
            metadata
            for pathname, (_, metadata) in self.objects.items()
            if pathname.startswith(prefix)
        ]

    def delete_blob(self, targets, *, if_match=None):
        if not isinstance(targets, str):
            assert len(targets) <= 1000
        for target in [targets] if isinstance(targets, str) else targets:
            if self.fail_cleanup and target.startswith("workspaces/"):
                raise BlobError("Temporary cleanup failure")
            if target in self.objects:
                if if_match is not None and if_match != self.objects[target][1].etag:
                    raise BlobPreconditionFailedError()
                del self.objects[target]


@pytest.fixture
def provider(monkeypatch):
    fake = FakeBlob()
    monkeypatch.setenv("BLOB_STORE_ID", "store-unit-test")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(cloud_store, "blob", fake)
    cloud_store.snapshot_bytes.cache_clear()
    yield fake
    cloud_store.snapshot_bytes.cache_clear()


def add(owner=OWNER, content=b"fake-pdf"):
    return store.add_document(
        owner,
        str(uuid.uuid4()),
        "guide.pdf",
        content,
        1,
        [{"page": 1, "text": "A documented policy."}],
        np.array([[1, 0, 0]], dtype=np.float32),
    )[0]


def test_private_snapshot_survives_fresh_worker_and_isolates_owners(provider):
    document_id = add()
    assert len(store.documents(OWNER)) == 1
    cloud_store.snapshot_bytes.cache_clear()  # Simulate losing the entire function's cache.
    assert store.get_document(OWNER, document_id)["pdf"] == b"fake-pdf"
    assert store.documents(OTHER) == []
    assert store.get_document(OTHER, document_id) is None
    assert not store.delete_document(OTHER, document_id)
    assert all(OWNER in path for path in provider.objects)


def test_anonymous_reads_do_not_allocate_storage(provider):
    assert store.documents(OWNER) == []
    assert provider.objects == {}


def test_duplicate_and_delete_are_persistent(provider):
    content = b"duplicate-content"
    first = add(content=content)
    assert add(content=content) == first
    assert len(provider.objects) == 1
    assert store.delete_document(OWNER, first)
    cloud_store.snapshot_bytes.cache_clear()
    assert store.documents(OWNER) == []
    assert store.get_chunks(OWNER, []) == []


def test_concurrent_writer_cannot_overwrite_active_lease(provider):
    with cloud_store.lease(OWNER):
        with pytest.raises(cloud_store.WorkspaceBusy):
            add()
        assert f"locks/{OWNER}.lock" in provider.objects
    assert provider.objects == {}


def test_expired_lease_can_be_recovered(provider):
    pathname = f"locks/{OWNER}.lock"
    lock = provider.put_blob(pathname, b"expired", access="private")
    lock.uploaded_at -= timedelta(seconds=cloud_store.LEASE_SECONDS + 1)
    add()
    assert pathname not in provider.objects
    assert len(store.documents(OWNER)) == 1


def test_failed_mutation_does_not_publish_partial_database(provider):
    with pytest.raises(ValueError):
        with store.database(OWNER, write=True) as db:
            db.execute("INSERT INTO metadata VALUES ('test', 'changed')")
            raise ValueError("Stop before commit")
    assert provider.objects == {}


def test_cleanup_failure_does_not_hide_committed_revision(provider):
    first = add(content=b"one")
    provider.fail_cleanup = True
    second = add(content=b"two")
    assert len(provider.objects) == 2
    cloud_store.snapshot_bytes.cache_clear()
    assert {d["id"] for d in store.documents(OWNER)} == {first, second}
    provider.fail_cleanup = False
    store.delete_document(OWNER, first)
    assert len(provider.objects) == 1
    assert [d["id"] for d in store.documents(OWNER)] == [second]


def test_cleanup_respects_provider_batch_limit(provider):
    add()
    original = next(iter(provider.objects.values()))[0]
    for index in range(2, 1003):
        provider.put_blob(
            f"workspaces/{OWNER}/{index:016d}-fixture.sqlite3", original, access="private"
        )
    add(content=b"another-document")
    assert len(provider.objects) == 1
    assert len(store.documents(OWNER)) == 2


def test_snapshot_deletion_during_read_retries(provider, monkeypatch):
    document_id = add()
    old_path = next(iter(provider.objects))
    original = provider.objects[old_path][0]
    real_get = provider.get_blob
    first = True

    def racing_get(pathname, **kwargs):
        nonlocal first
        if first:
            first = False
            provider.delete_blob(old_path)
            provider.put_blob(
                f"workspaces/{OWNER}/0000000000000002-race.sqlite3", original, access="private"
            )
            raise BlobNotFoundError()
        return real_get(pathname, **kwargs)

    monkeypatch.setattr(provider, "get_blob", racing_get)
    cloud_store.snapshot_bytes.cache_clear()
    assert store.get_document(OWNER, document_id)["pdf"] == b"fake-pdf"


def test_read_only_connection_refuses_mutations(provider):
    with pytest.raises(cloud_store.StorageUnavailable, match="read-only"):
        with store.database(OWNER) as db:
            db.execute("INSERT INTO metadata VALUES ('test', 'changed')")
    assert provider.objects == {}


def test_cloud_size_limit_fails_without_publishing(provider, monkeypatch):
    monkeypatch.setattr(cloud_store, "MAX_DATABASE_BYTES", 100)
    with pytest.raises(ValueError, match="32 MB"):
        add()
    assert provider.objects == {}


def test_cloud_requires_canonical_workspace_identifier(provider):
    with pytest.raises(cloud_store.StorageUnavailable, match="Invalid"):
        store.documents("../../another-workspace")
    assert provider.objects == {}


def test_cloud_model_fingerprint_is_checked(provider, monkeypatch):
    add()
    monkeypatch.setenv("EMBEDDING_MODEL", "another-model")
    with pytest.raises(RuntimeError, match="differs"):
        store.documents(OWNER)


def test_hosted_api_uses_secure_cookie_and_provider_storage(provider, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    monkeypatch.setattr(rag, "MAX_BYTES", 3 * 1024 * 1024)
    monkeypatch.setattr(
        rag,
        "embed",
        lambda texts, **kwargs: np.tile(np.array([[1, 0, 0]], dtype=np.float32), (len(texts), 1)),
    )
    RECENT.clear()
    with TestClient(app, base_url="https://testserver") as client:
        health = client.get("/api/health")
        assert health.json()["storage"] == "private-blob"
        assert health.json()["max_file_mb"] == 3
        assert "Secure" in health.headers["set-cookie"]
        result = client.post("/api/demo", headers={"Origin": "https://testserver"})
        assert result.status_code == 200
        assert len(client.get("/api/documents").json()) == 3
        assert client.post("/api/chat", json={"question": "When does it open?"}).status_code == 200
        assert client.post("/api/demo", headers={"Origin": "http://testserver"}).status_code == 403


def test_hosted_storage_failure_is_not_silent_local_fallback(provider, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("BLOB_STORE_ID")
    with pytest.raises(cloud_store.StorageUnavailable, match="Connect a private"):
        store.documents(OWNER)
