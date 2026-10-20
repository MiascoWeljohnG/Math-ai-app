"""Google Drive storage for uploaded course files.

Why OAuth and not a service account: a service account has no Drive storage quota of its own, so Google
refuses its uploads into a personal "My Drive" folder (403 "Service Accounts do not have storage quota").
Here the backend signs in as *you*, once, with a long-lived refresh token, so files are yours and count
against your Drive space.

Scope: `drive.file` - the app can only see files and folders it created itself. That is why DRIVE_FOLDER_ID
must be a folder made by tools/get_drive_token.py (a folder made by hand in the Drive website is invisible
to this scope).

Everything here raises DriveStorageError (message safe to show a teacher/admin) or its subclass
DriveFileNotFound. The google libraries are imported lazily so the app still starts without them
(local-disk mode).
"""
import io
import json
import logging
import mimetypes
import threading

import config

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_RESUMABLE_ABOVE = 5 * 1024 * 1024   # bigger uploads use Drive's resumable protocol
_RETRIES = 3                         # the client retries 429/5xx and network blips with backoff

_credentials = None
_credentials_lock = threading.Lock()


class DriveStorageError(RuntimeError):
    """Drive refused the request or couldn't be reached."""


class DriveFileNotFound(DriveStorageError):
    """The file isn't in Drive (deleted or moved to trash by hand)."""


def enabled() -> bool:
    """Should uploads go to Drive? "auto" means yes once every credential is configured."""
    if config.STORAGE_BACKEND == "local":
        return False
    if config.STORAGE_BACKEND == "drive":
        return True   # misconfiguration then surfaces as an error instead of a silent fallback to disk
    return not _missing_settings()


def backend_name() -> str:
    return "drive" if enabled() else "local"


def _missing_settings() -> list[str]:
    values = {
        "GOOGLE_CLIENT_ID": config.GOOGLE_CLIENT_ID,
        "GOOGLE_CLIENT_SECRET": config.GOOGLE_CLIENT_SECRET,
        "GOOGLE_REFRESH_TOKEN": config.GOOGLE_REFRESH_TOKEN,
        "DRIVE_FOLDER_ID": config.DRIVE_FOLDER_ID,
    }
    return [name for name, value in values.items() if not value]


def _service():
    missing = _missing_settings()
    if missing:
        raise DriveStorageError("Google Drive storage isn't configured (missing: " + ", ".join(missing) + ")")
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    global _credentials
    with _credentials_lock:
        if _credentials is None:
            _credentials = Credentials(
                token=None,   # fetched from the refresh token on first use, then renewed automatically
                refresh_token=config.GOOGLE_REFRESH_TOKEN,
                token_uri=_TOKEN_URI,
                client_id=config.GOOGLE_CLIENT_ID,
                client_secret=config.GOOGLE_CLIENT_SECRET,
                scopes=SCOPES,
            )
    # one service object per call: its HTTP transport (httplib2) isn't safe to share between threads
    return build("drive", "v3", credentials=_credentials, cache_discovery=False)


def _reason(exc) -> str:
    """Google's machine-readable error reason (e.g. storageQuotaExceeded), or ''."""
    try:
        return json.loads(exc.content)["error"]["errors"][0]["reason"]
    except Exception:
        return ""


def _translate(exc: Exception, doing: str, *, missing_means: str = "file") -> DriveStorageError:
    """Turn whatever the Google client raised into a DriveStorageError with a message that says what to do."""
    from google.auth.exceptions import RefreshError, TransportError
    from googleapiclient.errors import HttpError

    if isinstance(exc, DriveStorageError):
        return exc
    if isinstance(exc, RefreshError):
        return DriveStorageError(
            "Google rejected the saved login (the refresh token was revoked or expired). Run "
            "tools/get_drive_token.py again and update GOOGLE_REFRESH_TOKEN on the server. If the consent "
            "screen is still in 'Testing', publish it - Testing tokens expire after 7 days."
        )
    if isinstance(exc, HttpError):
        status = exc.resp.status
        reason = _reason(exc)
        if status == 404:
            if missing_means == "folder":
                return DriveStorageError(
                    "The Drive folder wasn't found. DRIVE_FOLDER_ID must be a folder created by "
                    "tools/get_drive_token.py - with the drive.file scope a folder made by hand is invisible."
                )
            return DriveFileNotFound("The file is no longer in Google Drive.")
        if status == 403 and reason == "storageQuotaExceeded":
            return DriveStorageError("The Google Drive account is out of storage space.")
        if status == 403 and reason in ("rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded"):
            return DriveStorageError("Google Drive is limiting requests right now. Try again in a minute.")
        if status == 401:
            return DriveStorageError("Google Drive rejected the login. Check GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN.")
        if status == 403:
            return DriveStorageError(f"Google Drive denied the request while {doing} ({reason or 'forbidden'}).")
        return DriveStorageError(f"Google Drive error {status} while {doing}" + (f" ({reason})." if reason else "."))
    if isinstance(exc, (TransportError, OSError, TimeoutError)):
        return DriveStorageError("Couldn't reach Google Drive. Try again in a moment.")
    return DriveStorageError(f"Unexpected Google Drive error while {doing} ({type(exc).__name__}).")


def _fail(exc: Exception, doing: str, **kwargs):
    translated = _translate(exc, doing, **kwargs)
    if translated is not exc:
        log.warning("Drive: %s failed: %r", doing, exc)
    raise translated from exc


def upload_bytes(name: str, data: bytes) -> str:
    """Store `data` as a new file in the configured folder; returns its Drive file id."""
    doing = f"uploading {name!r}"
    try:
        from googleapiclient.http import MediaIoBaseUpload

        media = MediaIoBaseUpload(
            io.BytesIO(data),
            mimetype=mimetypes.guess_type(name)[0] or "application/octet-stream",
            resumable=len(data) > _RESUMABLE_ABOVE,
        )
        created = _service().files().create(
            body={"name": name, "parents": [config.DRIVE_FOLDER_ID]},
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        ).execute(num_retries=_RETRIES)
        return created["id"]
    except Exception as exc:
        _fail(exc, doing, missing_means="folder")


def download_bytes(file_id: str) -> bytes:
    """The file's content. Raises DriveFileNotFound if it was deleted (or trashed) in Drive."""
    try:
        return _service().files().get_media(fileId=file_id, supportsAllDrives=True).execute(num_retries=_RETRIES)
    except Exception as exc:
        _fail(exc, "downloading a file")


def delete_file(file_id: str) -> None:
    """Move the file to the Drive trash (recoverable for 30 days). A file that's already gone counts as deleted."""
    try:
        _service().files().update(
            fileId=file_id, body={"trashed": True}, fields="id", supportsAllDrives=True,
        ).execute(num_retries=_RETRIES)
    except Exception as exc:
        translated = _translate(exc, "deleting a file")
        if isinstance(translated, DriveFileNotFound):
            return
        _fail(exc, "deleting a file")


def check() -> str:
    """Prove the credentials and the folder work. Returns the folder's name; raises DriveStorageError."""
    try:
        folder = _service().files().get(
            fileId=config.DRIVE_FOLDER_ID, fields="id,name,mimeType,trashed", supportsAllDrives=True,
        ).execute(num_retries=_RETRIES)
    except Exception as exc:
        _fail(exc, "opening the storage folder", missing_means="folder")
    if folder.get("mimeType") != "application/vnd.google-apps.folder":
        raise DriveStorageError("DRIVE_FOLDER_ID points at a file, not a folder.")
    if folder.get("trashed"):
        raise DriveStorageError("The storage folder is in the Drive trash. Restore it, or create a new one with tools/get_drive_token.py.")
    return folder["name"]
