"""Other devices can look, only the MITRA laptop can change things.

When the dashboard is shared (Cloudflare tunnel, or another device on the network),
requests reach the API through the dashboard's proxy, which records the original
visitor in X-Forwarded-For (the tunnel also adds Cf-Connecting-Ip). Any write
(POST/PUT/DELETE) from a non-local visitor is refused, so a shared link can view
everything and download reports but cannot edit prices or delete collectors.
The Telegram bot runs on the laptop and talks to the API directly, so it is unaffected.

Set MITRA_REMOTE_EDITS=1 (env or backend/.env) to allow edits from other devices.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import env_value

READ_METHODS = {"GET", "HEAD", "OPTIONS"}
REMOTE_EDIT_DENIED = ("Changes can only be made on the MITRA laptop. "
                      "Other devices can view everything and download reports.")


def _is_loopback(ip: str) -> bool:
    ip = ip.strip().lower()
    if ip.startswith("::ffff:"):
        ip = ip[len("::ffff:"):]
    return ip in {"127.0.0.1", "::1", "localhost"} or ip.startswith("127.")


def is_remote(request: Request) -> bool:
    if request.headers.get("cf-connecting-ip"):
        return True
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return any(not _is_loopback(ip) for ip in forwarded.split(",") if ip.strip())
    host = request.client.host if request.client else ""
    return bool(host) and host != "testclient" and not _is_loopback(host)


class RemoteReadOnly(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if (request.method not in READ_METHODS and is_remote(request)
                and env_value("MITRA_REMOTE_EDITS") != "1"):
            return JSONResponse({"detail": REMOTE_EDIT_DENIED}, status_code=403)
        return await call_next(request)
