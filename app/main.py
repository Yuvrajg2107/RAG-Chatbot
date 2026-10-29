"""Local-first PDF research workspace. Run with uvicorn app.main:app."""

import hashlib
import logging
import os
import re
import secrets
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import rag, store
from app.cloud_store import StorageUnavailable, WorkspaceBusy

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
LOG = logging.getLogger(__name__)
WORK = threading.BoundedSemaphore(2)
RATE_LOCK = threading.Lock()
RECENT = OrderedDict()


@asynccontextmanager
async def lifespan(app):
    store.initialize()
    yield


app = FastAPI(title="Margin · Document RAG", version="1.0.0", lifespan=lifespan)
allowed_hosts = ["localhost", "127.0.0.1", "testserver"]
allowed_hosts.extend(
    os.environ[name] for name in ("VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL") if os.getenv(name)
)
allowed_hosts.extend(
    value.strip() for value in os.getenv("ALLOWED_HOSTS", "").split(",") if value.strip()
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)


@app.exception_handler(StorageUnavailable)
async def storage_error(request: Request, error: StorageUnavailable):
    return JSONResponse(
        {"detail": str(error)}, status_code=409 if isinstance(error, WorkspaceBusy) else 503
    )


@app.middleware("http")
async def boundaries(request: Request, call_next):
    origin = request.headers.get("origin")
    scheme = "https" if os.getenv("VERCEL") else request.url.scheme
    if origin and origin != f"{scheme}://{request.headers.get('host')}":
        return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
    if request.method in {"POST", "PUT", "PATCH"}:
        cap = rag.MAX_BYTES + 1024 * 1024 if request.url.path == "/api/documents" else 32_768
        body = bytearray()
        async for part in request.stream():
            if len(body) + len(part) > cap:
                return JSONResponse({"detail": "Request is too large."}, status_code=413)
            body.extend(part)
        request._body = bytes(body)
    token = request.cookies.get("margin_session", "")
    new_session = not re.fullmatch(r"[a-f0-9]{64}", token)
    if new_session:
        token = secrets.token_hex(32)
    request.state.owner = hashlib.sha256(token.encode()).hexdigest()
    response = await call_next(request)
    if new_session:
        response.set_cookie(
            "margin_session",
            token,
            max_age=30 * 86400,
            httponly=True,
            samesite="strict",
            secure=os.getenv("COOKIE_SECURE", "true" if os.getenv("VERCEL") else "false").lower()
            == "true",
        )
    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        }
    )
    return response


def throttle(owner):
    with RATE_LOCK:
        now = time.monotonic()
        recent = [t for t in RECENT.pop(owner, []) if now - t < 60]
        if len(recent) >= 20:
            RECENT[owner] = recent
            raise HTTPException(429, "Too many requests. Please wait a minute.")
        RECENT[owner] = [*recent, now]
        while len(RECENT) > 1024:
            RECENT.popitem(last=False)


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    document_ids: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("question")
    @classmethod
    def not_blank(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Ask a question with at least three characters.")
        return value

    @field_validator("document_ids")
    @classmethod
    def valid_ids(cls, values):
        return list(dict.fromkeys(str(uuid.UUID(value)) for value in values))


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "mode": "gemini" if os.getenv("GEMINI_API_KEY", "").strip() else "extractive",
        "generation_model": os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        "embedding_model": os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        "retrieval_threshold": float(os.getenv("RETRIEVAL_THRESHOLD", "0.62")),
        "max_file_mb": rag.MAX_BYTES // (1024 * 1024),
        "max_pages": rag.MAX_PAGES,
        "storage": "private-blob" if store.cloud_enabled() else "local-sqlite",
        "hosted": bool(os.getenv("VERCEL")),
    }


@app.get("/api/documents")
def list_documents(request: Request):
    return store.documents(request.state.owner)


def ingest(owner, filename, content):
    if not WORK.acquire(blocking=False):
        raise HTTPException(503, "The workspace is busy. Please try again shortly.")
    try:
        chunks, pages = rag.chunks_from_pdf(content)
        vectors = rag.embed([chunk["text"] for chunk in chunks])
        document_id, duplicate = store.add_document(
            owner, str(uuid.uuid4()), filename, content, pages, chunks, vectors
        )
        document = next(d for d in store.documents(owner) if d["id"] == document_id)
        return {"document": document, "duplicate": duplicate}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except StorageUnavailable:
        raise
    except HTTPException:
        raise
    except Exception:
        LOG.exception("Document indexing failed")
        raise HTTPException(
            503,
            "Indexing failed. On first use, the embedding model needs an internet connection to download. Check the server log and retry.",
        ) from None
    finally:
        WORK.release()


@app.post("/api/documents", status_code=201)
def upload_document(request: Request, file: UploadFile):
    throttle(request.state.owner)
    try:
        filename = re.split(r"[/\\]", file.filename or "document.pdf")[-1][:120]
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(422, "Only PDF files are supported.")
        content = file.file.read(rag.MAX_BYTES + 1)
        if len(content) > rag.MAX_BYTES:
            raise HTTPException(
                413, f"Each PDF must be {rag.MAX_BYTES // (1024 * 1024)} MB or smaller."
            )
        return ingest(request.state.owner, filename, content)
    finally:
        file.file.close()


@app.post("/api/demo")
def load_demo(request: Request):
    throttle(request.state.owner)
    results = []
    for path in sorted((ROOT / "samples").glob("*.pdf")):
        results.append(ingest(request.state.owner, path.name, path.read_bytes()))
    if not results:
        raise HTTPException(
            503, "Sample PDFs are missing. Run uv run python scripts/create_samples.py."
        )
    return {"documents": results}


@app.delete("/api/documents/{document_id}", status_code=204)
def remove_document(document_id: uuid.UUID, request: Request):
    if not store.delete_document(request.state.owner, str(document_id)):
        raise HTTPException(404, "Document not found in this workspace.")
    return Response(status_code=204)


@app.get("/api/documents/{document_id}/file")
def download_document(document_id: uuid.UUID, request: Request):
    document = store.get_document(request.state.owner, str(document_id))
    if not document:
        raise HTTPException(404, "Document not found in this workspace.")
    from urllib.parse import quote

    return Response(
        document["pdf"],
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(document["filename"])
        },
    )


@app.post("/api/chat")
def chat(question: Question, request: Request):
    throttle(request.state.owner)
    if not WORK.acquire(blocking=False):
        raise HTTPException(503, "The workspace is busy. Please try again shortly.")
    started = time.monotonic()
    try:
        owned = {d["id"] for d in store.documents(request.state.owner)}
        if set(question.document_ids) - owned:
            raise HTTPException(
                404, "A selected document is no longer available in this workspace."
            )
        chunks = store.get_chunks(request.state.owner, question.document_ids)
        passages = rag.retrieve(question.question, chunks)
        result = rag.answer(question.question, passages)
        return result | {
            "retrieved": len(passages),
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
    except (HTTPException, StorageUnavailable):
        raise
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(503, str(exc)) from None
    except Exception:
        LOG.exception("Question answering failed")
        raise HTTPException(
            503, "Question answering is unavailable. Check the server log and retry."
        ) from None
    finally:
        WORK.release()


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
