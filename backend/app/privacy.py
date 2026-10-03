"""Signed, HttpOnly guest identity. No public read access to ownerless history.

The token is an access credential, never an author label. Store only a one-way
owner identifier in cases; keep the signing secret outside published assets.
"""
import hashlib
import hmac
import os
import re
import secrets
import time
from contextvars import ContextVar
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from app import config
from app.persistence import atomic_text, locked

OWNER: ContextVar[str | None] = ContextVar("guest_owner", default=None)
GUEST: ContextVar[str | None] = ContextVar("guest_identity", default=None)  # 匿名身份；登录后 OWNER 换成账号，它不变
ACCOUNT: ContextVar[dict | None] = ContextVar("account", default=None)
CLIENT_IP: ContextVar[str] = ContextVar("client_ip", default="")
LIFETIME = 180 * 86400
COOKIE = "qier_guest"
SECURE_COOKIE = "__Host-qier_guest"


def identity() -> str:
    owner = OWNER.get()
    if not owner:
        raise RuntimeError("Private operation needs a guest identity")
    return owner


def private_dir() -> Path:
    return Path(os.getenv("XRAY_PRIVATE_DIR", str(config.CASES_DIR.parent / "private")))


def secret() -> bytes:
    path = private_dir() / "guest-signing.secret"
    with locked(path):
        if not path.exists():
            atomic_text(path, secrets.token_hex(32))
            path.chmod(0o600)
        value = path.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RuntimeError("Invalid guest signing secret")
    return bytes.fromhex(value)


def issue() -> str:
    payload = f"{secrets.token_hex(32)}.{int(time.time())}"
    signature = hmac.new(secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def owner_from_token(token: str | None) -> str | None:
    if not token or not re.fullmatch(r"[0-9a-f]{64}\.[0-9]{10,12}\.[0-9a-f]{64}", token):
        return None
    payload, signature = token.rsplit(".", 1)
    age = time.time() - int(payload.split(".")[1])
    if age < -60 or age > LIFETIME:
        return None
    expected = hmac.new(secret(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    return hashlib.sha256(payload.split(".")[0].encode()).hexdigest()


def client_ip(request: Request) -> str:
    """Cloudflare 填 CF-Connecting-IP；没经过它时退到代理头，再退到连接地址。只用来计数，不用来鉴权。"""
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",")[0]
    return forwarded.strip()[:64] or (request.client.host if request.client else "")


def allowed_origins() -> list[str]:
    return [s.strip().rstrip("/") for s in os.getenv("XRAY_ALLOWED_ORIGINS", "").split(",") if s.strip()]


class GuestPrivacyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        path = request.url.path
        api = path.startswith("/api/")
        if api and request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            same_origin = str(request.base_url).rstrip("/")
            if request.headers.get("sec-fetch-site") == "cross-site" or (
                origin and origin != same_origin and origin not in allowed_origins()
            ):
                return await JSONResponse({"detail": "请从本站页面提交请求"}, status_code=403)(scope, receive, send)
        secure = request.url.scheme == "https"
        name = SECURE_COOKIE if secure else COOKIE
        token = request.cookies.get(name)
        owner = owner_from_token(token)
        # Establish identity on document load, before parallel API calls start.
        needs_identity = path in {"/", "/index.html", "/xray", "/xray/", "/xray/index.html", "/api/session"} or (
            api and (path.startswith(("/api/cases", "/api/runs")) or request.method == "POST")
        )
        fresh = needs_identity and not owner
        if fresh:
            token = issue()
            owner = owner_from_token(token)
        from app import accounts  # 账号模块要用这里的签名密钥，放到调用时再导入
        user_token = request.cookies.get(accounts.cookie_name(secure))
        account = accounts.from_session(user_token) if user_token else None
        stale_user = bool(user_token) and account is None
        context_token = OWNER.set(accounts.owner(account) if account else owner)
        guest_token, account_token = GUEST.set(owner), ACCOUNT.set(account)
        ip_token = CLIENT_IP.set(client_ip(request))

        async def private_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if api or fresh:
                    headers = [(k, v) for k, v in headers if k.lower() not in {b"cache-control", b"vary"}]
                    headers += [(b"cache-control", b"private, no-store"), (b"vary", b"Cookie, Origin")]
                if fresh:
                    cookie = f"{name}={token}; Path=/; Max-Age={LIFETIME}; HttpOnly; SameSite=Lax"
                    if secure:
                        cookie += "; Secure"
                    headers.append((b"set-cookie", cookie.encode("ascii")))
                if stale_user and not any(k.lower() == b"set-cookie" and v.startswith(accounts.cookie_name(secure).encode())
                                          for k, v in headers):
                    headers.append((b"set-cookie", accounts.clear_cookie(secure).encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, private_send)
        finally:
            OWNER.reset(context_token)
            GUEST.reset(guest_token)
            ACCOUNT.reset(account_token)
            CLIENT_IP.reset(ip_token)
