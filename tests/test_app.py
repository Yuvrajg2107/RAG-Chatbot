"""Isolated API regression tests. Embeddings are stubbed; real model tests run via evaluate."""

import io
import json
import uuid

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from reportlab.pdfgen import canvas

from app import rag, store
from app.main import RECENT, app


def pdf(text="The library opens at 8 AM."):
    output = io.BytesIO()
    document = canvas.Canvas(output)
    document.drawString(30, 760, text)
    document.save()
    return output.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("RETRIEVAL_THRESHOLD", "0.62")
    monkeypatch.setattr(
        rag,
        "embed",
        lambda texts, **kwargs: np.tile(np.array([[1, 0, 0]], dtype=np.float32), (len(texts), 1)),
    )
    RECENT.clear()
    with TestClient(app) as session:
        yield session


def upload(client, content=None, filename="guide.pdf"):
    return client.post(
        "/api/documents", files={"file": (filename, content or pdf(), "application/pdf")}
    )


def test_empty_workspace_abstains(client):
    response = client.post("/api/chat", json={"question": "When does it open?"})
    assert response.status_code == 200
    assert response.json()["answerable"] is False
    assert response.json()["citations"] == []


def test_upload_chat_citation_download_and_delete(client):
    response = upload(client)
    assert response.status_code == 201
    doc = response.json()["document"]
    assert doc["pages"] == 1 and doc["chunks"] == 1
    answer = client.post(
        "/api/chat", json={"question": "When does the library open?", "document_ids": [doc["id"]]}
    ).json()
    assert answer["mode"] == "extractive" and answer["answerable"] is None
    assert "8 AM" in answer["answer"]
    assert answer["citations"][0]["page"] == 1
    assert answer["citations"][0]["document_id"] == doc["id"]
    source = client.get(f"/api/documents/{doc['id']}/file")
    assert source.status_code == 200 and source.content.startswith(b"%PDF-")
    assert "attachment" in source.headers["content-disposition"]
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get("/api/documents").json() == []
    assert client.get(f"/api/documents/{doc['id']}/file").status_code == 404


def test_duplicate_upload_is_idempotent(client):
    content = pdf()
    first, second = upload(client, content).json(), upload(client, content).json()
    assert first["document"]["id"] == second["document"]["id"]
    assert second["duplicate"] is True
    assert len(client.get("/api/documents").json()) == 1


def test_workspace_isolation(client):
    doc = upload(client).json()["document"]
    with TestClient(app) as other:
        assert other.get("/api/documents").json() == []
        assert other.get(f"/api/documents/{doc['id']}/file").status_code == 404
        assert other.delete(f"/api/documents/{doc['id']}").status_code == 404
        assert (
            other.post(
                "/api/chat", json={"question": "When does it open?", "document_ids": [doc["id"]]}
            ).status_code
            == 404
        )


@pytest.mark.parametrize(
    "filename,content",
    [("guide.txt", b"not pdf"), ("guide.pdf", b"not pdf"), ("guide.pdf", b"%PDF-broken")],
)
def test_invalid_files_rejected(client, filename, content):
    assert upload(client, content, filename).status_code == 422
    assert client.get("/api/documents").json() == []


def test_empty_and_encrypted_pdfs_rejected(client):
    blank = PdfWriter()
    blank.add_blank_page(width=100, height=100)
    output = io.BytesIO()
    blank.write(output)
    assert upload(client, output.getvalue()).status_code == 422
    blank.encrypt("test-password")
    output = io.BytesIO()
    blank.write(output)
    assert upload(client, output.getvalue()).status_code == 422


def test_size_limit_and_path_filename(client):
    assert upload(client, b"%PDF-" + b"x" * rag.MAX_BYTES).status_code == 413
    response = upload(client, filename="../../guide.pdf")
    assert response.json()["document"]["filename"] == "guide.pdf"


@pytest.mark.parametrize(
    "body",
    [
        {"question": "  "},
        {"question": "a" * 1001},
        {"question": "Hello?", "document_ids": ["not-a-uuid"]},
    ],
)
def test_invalid_questions(client, body):
    assert client.post("/api/chat", json=body).status_code == 422


@pytest.mark.parametrize("limit", [0, -1, 11, 1.5, True, "5", None])
def test_invalid_retrieval_limits(client, limit):
    response = client.post(
        "/api/chat", json={"question": "When does it open?", "retrieval_limit": limit}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("limit,expected", [(None, 5), (1, 1), (5, 5), (10, 10)])
def test_chat_applies_retrieval_limit(client, monkeypatch, limit, expected):
    content = io.BytesIO()
    document = canvas.Canvas(content)
    for page in range(12):
        document.drawString(30, 760, f"Library policy on page {page + 1}: opens at 8 AM.")
        document.showPage()
    document.save()
    doc = upload(client, content.getvalue()).json()["document"]
    body = {"question": "When does the library open?", "document_ids": [doc["id"]]}
    if limit is not None:
        body["retrieval_limit"] = limit
    received = []
    original_answer = rag.answer

    def capture_answer(question, passages):
        received.extend(passages)
        return original_answer(question, passages)

    monkeypatch.setattr(rag, "answer", capture_answer)
    response = client.post("/api/chat", json=body)
    assert response.status_code == 200
    assert response.json()["retrieved"] == expected
    assert len(received) == expected
    assert {passage["document_id"] for passage in received} == {doc["id"]}


def test_security_headers_and_origin(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "script-src 'self'" in response.headers["content-security-policy"]
    cookie = client.cookies.get("margin_session")
    assert len(cookie) == 64
    assert (
        client.post("/api/demo", headers={"Origin": "https://attacker.example"}).status_code == 403
    )
    assert client.get("/api/health", headers={"Host": "attacker.example"}).status_code == 400


def test_throttling(client):
    for _ in range(20):
        assert client.post("/api/chat", json={"question": "What is this?"}).status_code == 200
    assert client.post("/api/chat", json={"question": "What is this?"}).status_code == 429


def test_model_fingerprint_rejects_mixed_embeddings(client, monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL", "another-model")
    with pytest.raises(RuntimeError, match="differs"):
        store.initialize()


def test_document_filter(client):
    first = upload(client, pdf("Alpha policy says apples.")).json()["document"]
    second = upload(client, pdf("Beta policy says bananas.")).json()["document"]
    result = client.post(
        "/api/chat", json={"question": "What is the policy?", "document_ids": [second["id"]]}
    ).json()
    assert result["citations"][0]["document_id"] == second["id"]
    assert result["citations"][0]["document_id"] != first["id"]


def test_long_pages_are_chunked_with_page_numbers():
    content = io.BytesIO()
    doc = canvas.Canvas(content)
    text = doc.beginText(20, 780)
    for _ in range(20):
        text.textLine("This is a repeated sentence with enough text to require overlapping chunks.")
    doc.drawText(text)
    doc.showPage()
    doc.drawString(20, 780, "Second page has a different source.")
    doc.save()
    chunks, pages = rag.chunks_from_pdf(content.getvalue())
    assert pages == 2 and len(chunks) >= 3
    assert {chunk["page"] for chunk in chunks} == {1, 2}
    assert all(len(chunk["text"]) <= rag.CHUNK_SIZE for chunk in chunks)


def test_retrieval_threshold_and_top_k(monkeypatch):
    monkeypatch.setattr(rag, "embed", lambda *args, **kwargs: np.array([[1, 0]], dtype=np.float32))
    monkeypatch.setenv("RETRIEVAL_THRESHOLD", "0.62")
    chunks = [
        {
            "document_id": str(uuid.uuid4()),
            "page": 1,
            "filename": "test.pdf",
            "text": f"passage {i}",
            "vector": np.array(vector, dtype=np.float32).tobytes(),
        }
        for i, vector in enumerate([[1, 0], [0, 1], [0.8, 0.6]])
    ]
    found = rag.retrieve("What is in the passage?", chunks, limit=1)
    assert len(found) == 1 and found[0]["text"] == "passage 0"
    assert rag.retrieve("Unrelated", [chunks[1]]) == []


@pytest.fixture
def passage():
    return [
        {
            "document_id": str(uuid.uuid4()),
            "filename": "guide.pdf",
            "page": 2,
            "text": "The library opens at 8 AM on weekdays.",
            "score": 0.8,
        }
    ]


def gemini_response(monkeypatch, payload, status=200):
    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-not-a-real-key")

    def fake_post(url, **kwargs):
        request = httpx.Request("POST", url)
        data = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}
        return httpx.Response(status, json=data, request=request)

    monkeypatch.setattr(rag.httpx, "post", fake_post)


def test_gemini_grounded_claim(monkeypatch, passage):
    gemini_response(
        monkeypatch,
        {
            "answerable": True,
            "claims": [
                {
                    "text": "The library opens at 8 AM.",
                    "source": 1,
                    "quote": "The library opens at 8 AM",
                }
            ],
        },
    )
    result = rag.answer("When does it open?", passage)
    assert result["answerable"] is True and result["mode"] == "gemini"
    assert result["citations"][0]["page"] == 2 and "[1]" in result["answer"]


@pytest.mark.parametrize(
    "claim",
    [
        {"text": "Opens at 8.", "source": 99, "quote": "The library opens at 8 AM"},
        {"text": "Opens at 8.", "source": True, "quote": "The library opens at 8 AM"},
        {"text": "Opens at 8.", "source": 1, "quote": "Fabricated quote from nowhere"},
        {"text": "Opens at 8.", "source": 1, "quote": ""},
        {"text": "Opens at 8.", "source": 1, "quote": "THE LIBRARY OPENS AT 8 AM"},
    ],
)
def test_gemini_rejects_invalid_citations(monkeypatch, passage, claim):
    gemini_response(monkeypatch, {"answerable": True, "claims": [claim]})
    assert rag.answer("When?", passage)["answerable"] is False


def test_gemini_abstains_and_quota_errors(monkeypatch, passage):
    gemini_response(monkeypatch, {"answerable": False, "claims": []})
    assert rag.answer("Who is the librarian?", passage)["answerable"] is False
    gemini_response(monkeypatch, {}, status=429)
    with pytest.raises(RuntimeError, match="quota"):
        rag.answer("When?", passage)
    gemini_response(monkeypatch, {}, status=402)
    with pytest.raises(RuntimeError, match="prepaid credits"):
        rag.answer("When?", passage)


def test_gemini_rejects_non_object_response(monkeypatch, passage):
    gemini_response(monkeypatch, ["invalid response"])
    with pytest.raises(RuntimeError, match="invalid response"):
        rag.answer("When?", passage)


def test_document_id_canonicalization(client):
    document = upload(client).json()["document"]
    result = client.post(
        "/api/chat",
        json={"question": "When does the library open?", "document_ids": [document["id"].upper()]},
    )
    assert result.status_code == 200
    assert result.json()["citations"][0]["document_id"] == document["id"]


def test_sample_corpus_has_required_questions():
    from pathlib import Path

    questions = json.loads(Path("evaluation/questions.json").read_text())
    assert len(questions) >= 20
    assert sum(not q["answerable"] for q in questions) >= 5
    assert all(q["expected_page"] for q in questions if q["answerable"])


def test_page_and_request_size_limits(client):
    writer = PdfWriter()
    for _ in range(rag.MAX_PAGES + 1):
        writer.add_blank_page(width=100, height=100)
    output = io.BytesIO()
    writer.write(output)
    assert upload(client, output.getvalue()).status_code == 422
    assert client.post("/api/chat", content=b"x" * 33_000).status_code == 413


def test_storage_quota_and_transaction_rollback(client):
    chunks = [{"page": 1, "text": "A source passage."}]
    vectors = np.array([[1, 0, 0]], dtype=np.float32)
    for index in range(20):
        store.add_document(
            "quota", str(uuid.uuid4()), "a.pdf", f"pdf {index}".encode(), 1, chunks, vectors
        )
    with pytest.raises(ValueError, match="limited to 20"):
        store.add_document("quota", str(uuid.uuid4()), "a.pdf", b"another pdf", 1, chunks, vectors)
    assert len(store.documents("quota")) == 20
    with pytest.raises(ValueError):
        store.add_document("rollback", str(uuid.uuid4()), "a.pdf", b"pdf", 1, chunks, [])
    assert store.documents("rollback") == []


def test_submission_package_excludes_private_data(tmp_path, monkeypatch):
    from zipfile import ZipFile

    from scripts import package as packager

    monkeypatch.setattr(packager, "ROOT", tmp_path)
    for name in [
        "README.md",
        ".env.example",
        ".env",
        ".env.local",
        ".vercel/.env.production.local",
        "app/.env.local",
        "app/.vercel/private.json",
        "data/private.pdf",
        "app/main.py",
        "app/__pycache__/x.pyc",
    ]:
        file = tmp_path / name
        file.parent.mkdir(exist_ok=True, parents=True)
        file.write_text("fixture")
    archive = packager.package(tmp_path / "submission.zip")
    with ZipFile(archive) as zipped:
        assert set(zipped.namelist()) == {
            "margin-rag/README.md",
            "margin-rag/.env.example",
            "margin-rag/app/main.py",
        }
