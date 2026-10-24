"""Tiny in-memory rate limiter for the public sign-up endpoints (each upload costs storage).
One process only: with several server instances use a shared store (Redis) instead - same call sites."""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_hits: dict[tuple[str, str], deque] = defaultdict(deque)
_lock = threading.Lock()


def client_ip(request: Request) -> str:
    # Behind Render's proxy the peer is the proxy; it appends the real client address to X-Forwarded-For,
    # so the LAST entry is the one we can trust (earlier ones are client-supplied).
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[-1].strip() if forwarded else (request.client.host if request.client else "unknown")


def limit(request: Request, bucket: str, max_hits: int, per_seconds: int) -> None:
    now, key = time.monotonic(), (bucket, client_ip(request))
    with _lock:
        q = _hits[key]
        while q and now - q[0] > per_seconds:
            q.popleft()
        if len(q) >= max_hits:
            raise HTTPException(status_code=429, detail="Too many attempts. Please wait a while and try again.")
        q.append(now)


def reset() -> None:   # for tests
    with _lock:
        _hits.clear()
