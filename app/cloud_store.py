"""Private Blob-backed SQLite snapshots for a small, single-region Vercel demo.

Objects are immutable so CDN caches cannot return an outdated overwritten database.
A conditional-create lease serializes each workspace's writes across function instances.
This trades Blob operations for a zero-service database setup, not high throughput.
"""

import logging
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache

from vercel.blob import BlobError, BlobNotFoundError
from vercel.blob import sync as blob

LOG = logging.getLogger(__name__)
MAX_DATABASE_BYTES = 32 * 1024 * 1024
LEASE_SECONDS = 180  # Must exceed vercel.json's 60-second function duration.


class StorageUnavailable(RuntimeError):
    pass


class WorkspaceBusy(StorageUnavailable):
    pass


@lru_cache(maxsize=4)
def snapshot_bytes(pathname):
    content = blob.get_blob(pathname, access="private").body
    if len(content) > MAX_DATABASE_BYTES:
        raise StorageUnavailable("The workspace exceeds the hosted storage limit.")
    return content


def latest_snapshot(prefix):
    # Reads can overlap deletion of a superseded snapshot. Re-list once in that case.
    for _ in range(2):
        snapshots = sorted(blob.query_blobs(prefix=prefix), key=lambda item: item.pathname)
        if not snapshots:
            return None, b"", []
        latest = snapshots[-1]
        try:
            return latest.pathname, snapshot_bytes(latest.pathname), snapshots
        except BlobNotFoundError:
            continue
    raise StorageUnavailable("Workspace data changed while reading. Please retry.")


@contextmanager
def lease(owner):
    pathname = f"locks/{owner}.lock"
    try:
        lock = blob.put_blob(pathname, secrets.token_bytes(32), access="private")
    except BlobError:
        # A crashed function may leave a lease. Only remove an expired lease by its ETag.
        try:
            existing = blob.head_blob(pathname)
        except BlobNotFoundError:
            raise WorkspaceBusy("Workspace is busy. Please retry shortly.") from None
        if (datetime.now(UTC) - existing.uploaded_at).total_seconds() < LEASE_SECONDS:
            raise WorkspaceBusy("Workspace is busy. Please retry shortly.") from None
        try:
            blob.delete_blob(pathname, if_match=existing.etag)
            lock = blob.put_blob(pathname, secrets.token_bytes(32), access="private")
        except BlobError:
            raise WorkspaceBusy("Workspace is busy. Please retry shortly.") from None
    try:
        yield
    finally:
        try:
            blob.delete_blob(pathname, if_match=lock.etag)
        except BlobError:
            LOG.warning("Workspace lease cleanup failed; expiry will permit recovery.")


@contextmanager
def connection(owner, setup, *, write=False):
    if not re.fullmatch(r"[a-f0-9]{64}", owner):
        raise StorageUnavailable("Invalid workspace identifier.")
    try:
        if write:
            with lease(owner):
                with workspace_connection(owner, setup, write=True) as database:
                    yield database
        else:
            with workspace_connection(owner, setup, write=False) as database:
                yield database
    except BlobError:
        raise StorageUnavailable("Hosted storage is unavailable. Please retry later.") from None


@contextmanager
def workspace_connection(owner, setup, *, write):
    prefix = f"workspaces/{owner}/"
    previous, content, snapshots = latest_snapshot(prefix)
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    try:
        if content:
            database.deserialize(content)
        database.execute("PRAGMA foreign_keys=ON")
        setup(database)
        baseline = database.total_changes
        yield database
        database.commit()
        if database.total_changes == baseline:
            return
        if not write:
            raise StorageUnavailable("A read-only storage operation attempted a write.")
        content = database.serialize()
        if len(content) > MAX_DATABASE_BYTES:
            raise ValueError(
                "Hosted workspaces are limited to 32 MB of PDFs and index data. Remove a PDF before uploading more."
            )
        revision = int(previous.rsplit("/", 1)[-1].split("-", 1)[0]) + 1 if previous else 1
        pathname = f"{prefix}{revision:016d}-{secrets.token_hex(8)}.sqlite3"
        blob.put_blob(pathname, content, access="private", content_type="application/octet-stream")
        # The new revision is committed. Cleanup failure must not turn success into a retry.
        for offset in range(0, len(snapshots), 1000):
            try:
                blob.delete_blob([item.pathname for item in snapshots[offset : offset + 1000]])
            except BlobError:
                LOG.warning(
                    "Old workspace snapshots could not be removed; a later write will retry cleanup."
                )
                break
    finally:
        database.close()
