"""SQLite is the persistent vector store for this small, single-instance workspace."""

import hashlib
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, owner TEXT NOT NULL, filename TEXT NOT NULL,
    digest TEXT NOT NULL, pages INTEGER NOT NULL, size INTEGER NOT NULL,
    pdf BLOB NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(owner, digest)
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page INTEGER NOT NULL, text TEXT NOT NULL, vector BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS documents_owner ON documents(owner);
CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def cloud_enabled():
    return bool(os.getenv("BLOB_STORE_ID"))


@contextmanager
def database(owner=None, *, write=False):
    if cloud_enabled():
        from app.cloud_store import connection

        with connection(owner, setup, write=write) as db:
            yield db
        return
    if os.getenv("VERCEL"):
        from app.cloud_store import StorageUnavailable

        raise StorageUnavailable("Connect a private Blob store before using the hosted workspace.")
    directory = Path(os.getenv("DATA_DIR", "data"))
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(directory / "margin.sqlite3", timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def setup(db):
    db.executescript(SCHEMA)
    model = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    existing = db.execute("SELECT value FROM metadata WHERE key='embedding_model'").fetchone()
    if existing and existing[0] != model:
        raise RuntimeError(
            "Embedding model differs from this database. Use a new DATA_DIR or restore EMBEDDING_MODEL."
        )
    db.execute("INSERT OR IGNORE INTO metadata VALUES ('embedding_model', ?)", (model,))
    db.commit()


def initialize():
    if cloud_enabled():
        return  # Each private workspace snapshot has its own schema/model fingerprint.
    with database() as db:
        setup(db)


def documents(owner: str) -> list[dict]:
    with database(owner) as db:
        return [
            dict(row)
            for row in db.execute(
                "SELECT d.id,d.filename,d.pages,d.size,d.created_at,COUNT(c.id) AS chunks "
                "FROM documents d LEFT JOIN chunks c ON c.document_id=d.id "
                "WHERE d.owner=? GROUP BY d.id ORDER BY d.created_at,d.filename",
                (owner,),
            )
        ]


def add_document(owner, document_id, filename, content, pages, chunks, vectors):
    digest = hashlib.sha256(content).hexdigest()
    with database(owner, write=True) as db:
        # Lock before quota/duplicate checks so simultaneous uploads cannot bypass limits.
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT id FROM documents WHERE owner=? AND digest=?", (owner, digest)
        ).fetchone()
        if existing:
            return existing[0], True
        count = db.execute("SELECT COUNT(*) FROM documents WHERE owner=?", (owner,)).fetchone()[0]
        if count >= 20:
            raise ValueError(
                "This workspace is limited to 20 PDFs. Remove a document before uploading more."
            )
        db.execute(
            "INSERT INTO documents(id,owner,filename,digest,pages,size,pdf) VALUES (?,?,?,?,?,?,?)",
            (document_id, owner, filename, digest, pages, len(content), content),
        )
        db.executemany(
            "INSERT INTO chunks(document_id,page,text,vector) VALUES (?,?,?,?)",
            [
                (
                    document_id,
                    chunk["page"],
                    chunk["text"],
                    np.asarray(vector, dtype=np.float32).tobytes(),
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ],
        )
    return document_id, False


def get_chunks(owner: str, document_ids: list[str]) -> list[dict]:
    with database(owner) as db:
        params = [owner]
        query = (
            "SELECT c.id,c.document_id,c.page,c.text,c.vector,d.filename FROM chunks c "
            "JOIN documents d ON c.document_id=d.id WHERE d.owner=?"
        )
        if document_ids:
            query += " AND d.id IN (" + ",".join("?" for _ in document_ids) + ")"
            params.extend(document_ids)
        return [dict(row) for row in db.execute(query, params)]


def get_document(owner: str, document_id: str):
    with database(owner) as db:
        row = db.execute(
            "SELECT * FROM documents WHERE id=? AND owner=?", (document_id, owner)
        ).fetchone()
        return dict(row) if row else None


def delete_document(owner: str, document_id: str) -> bool:
    with database(owner, write=True) as db:
        return (
            db.execute(
                "DELETE FROM documents WHERE id=? AND owner=?", (document_id, owner)
            ).rowcount
            > 0
        )
