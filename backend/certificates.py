"""Enrollment certificates: validate what was uploaded and keep it in private storage.

* The type is decided from the file's first bytes, never from its name or the browser's Content-Type.
* The stored name is random; the student's file name is kept only as a label.
* Storage follows the app's existing choice: Google Drive when configured (survives Render restarts), otherwise a
  private folder on disk. The reference is never sent to the browser - reviewers read files through
  GET /approvals/{username}/certificate, which checks who is asking.
"""
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

import config
import drive_storage

_SIGNATURES = (
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
)
_LOCAL_NAME = re.compile(r"[0-9a-f]{32}\.(pdf|png|jpg)")


def sniff(data: bytes) -> tuple[str, str]:
    for magic, content_type, ext in _SIGNATURES:
        if data.startswith(magic):
            return content_type, ext
    raise HTTPException(status_code=400, detail="The certificate must be a PDF, PNG or JPG file.")


async def read_upload(file: UploadFile) -> bytes:
    """Read the upload, refusing anything over the size limit without loading all of it."""
    data = await file.read(config.CERT_MAX_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="The certificate file is empty.")
    if len(data) > config.CERT_MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"The certificate must be under {config.CERT_MAX_BYTES // (1024 * 1024)} MB.")
    return data


def save(data: bytes, ext: str) -> str:
    name = uuid.uuid4().hex + ext
    if drive_storage.enabled():
        try:
            return "drive:" + drive_storage.upload_bytes("cert_" + name, data)
        except drive_storage.DriveStorageError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
    folder = Path(config.CERT_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)
    return "local:" + name


def load(ref: str) -> bytes:
    kind, _, value = ref.partition(":")
    if kind == "drive":
        try:
            return drive_storage.download_bytes(value)
        except drive_storage.DriveStorageError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
    if kind == "local" and _LOCAL_NAME.fullmatch(value):   # the pattern also rules out path tricks
        path = Path(config.CERT_DIR) / value
        if path.is_file():
            return path.read_bytes()
    raise HTTPException(status_code=404, detail="The certificate file is no longer available.")


def delete(ref: str) -> None:
    """Best effort clean-up (a registration that failed after the file was stored)."""
    kind, _, value = ref.partition(":")
    try:
        if kind == "drive":
            drive_storage.delete_file(value)
        elif kind == "local" and _LOCAL_NAME.fullmatch(value):
            (Path(config.CERT_DIR) / value).unlink(missing_ok=True)
    except Exception:
        pass
