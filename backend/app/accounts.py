"""可选的邮箱账号：换设备找回案卷和资料库。

- 只存邮箱和 scrypt 密码哈希；不登录照常能用，匿名身份见 privacy.py。
- 登录 cookie 是 `账号id.代数.签发时间.签名`。改密码、找回、注销都会把代数加一，旧登录全部失效。
- 找回令牌的签名覆盖当前密码哈希：改过一次密码，旧令牌自然作废。
- 频率记录放在文件里，多个进程共享；邮箱只以哈希出现在这些记录里。
"""
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
from pathlib import Path

import httpx

from app import privacy
from app.persistence import atomic_json, atomic_text, locked

log = logging.getLogger("xray.accounts")

LIFETIME = privacy.LIFETIME
COOKIE, SECURE_COOKIE = "qier_user", "__Host-qier_user"
RESET_TTL = 30 * 60
LOGIN_WINDOW, LOGIN_FAILS, LOGIN_FAILS_IP = 15 * 60, 5, 30
MAIL_GAP, MAIL_PER_IP_HOUR = 120, 5
LIBRARY_MAX = 500
EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s.]+(\.[^@\s.]+)+")
ACCOUNT_ID = re.compile(r"[0-9a-f]{24}")
SCRYPT = (2 ** 14, 8, 1)


class AccountError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def root() -> Path:
    return privacy.private_dir() / "accounts"


def cookie_name(secure: bool) -> str:
    return SECURE_COOKIE if secure else COOKIE


def clear_cookie(secure: bool) -> str:
    return f"{cookie_name(secure)}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax" + ("; Secure" if secure else "")


def owner(account: dict) -> str:
    return f"acct-{account['id']}"


def public(account: dict | None) -> dict | None:
    return {"email": account["email"]} if account else None


# ---------- 输入 ----------

def normalize_email(value: str) -> str:
    email = (value or "").strip().lower()
    if len(email) > 254 or not EMAIL.fullmatch(email):
        raise AccountError(422, "邮箱格式不对")
    return email


def check_password(value: str) -> str:
    if not 8 <= len(value or "") <= 128:
        raise AccountError(422, "密码要 8 到 128 位")
    return value


def _email_key(email: str) -> str:
    return hashlib.sha256(email.encode()).hexdigest()


# ---------- 密码与签名 ----------

def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    n, r, p = SCRYPT
    digest = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got.hex(), digest)
    except (ValueError, TypeError):
        return False


_DUMMY = _hash_password("not-a-real-password")


def _sign(kind: str, payload: str) -> str:
    return hmac.new(privacy.secret(), f"{kind}|{payload}".encode(), hashlib.sha256).hexdigest()


# ---------- 账号文件 ----------

def _path(account_id: str) -> Path:
    if not ACCOUNT_ID.fullmatch(account_id or ""):
        raise KeyError(account_id)
    return root() / f"{account_id}.json"


def load(account_id: str) -> dict | None:
    try:
        return json.loads(_path(account_id).read_text(encoding="utf-8"))
    except (KeyError, OSError, ValueError):
        return None


def _by_email(email: str) -> dict | None:
    try:
        return load((root() / "by-email" / _email_key(email)).read_text(encoding="utf-8").strip())
    except OSError:
        return None


def _save(account: dict) -> dict:
    atomic_json(_path(account["id"]), account)
    return account


def register(email: str, password: str) -> dict:
    email, password = normalize_email(email), check_password(password)
    index = root() / "by-email" / _email_key(email)
    with locked(index):
        if index.exists() and _by_email(email):
            raise AccountError(409, "这个邮箱已经注册过，可以直接登录；忘了密码可以找回")
        account = {"id": secrets.token_hex(12), "email": email, "pw": _hash_password(password), "gen": 1,
                   "created_at": int(time.time())}
        _save(account)
        atomic_text(index, account["id"])
    return account


def login(email: str, password: str, ip: str) -> dict:
    email = normalize_email(email)
    key = _email_key(email)
    if _hits("login-fail", key, LOGIN_WINDOW) >= LOGIN_FAILS or _hits("login-fail-ip", ip, LOGIN_WINDOW) >= LOGIN_FAILS_IP:
        raise AccountError(429, "密码错误次数太多，请 15 分钟后再试，或者找回密码")
    account = _by_email(email)
    if not _verify_password(password or "", account["pw"] if account else _DUMMY) or account is None:
        _hits("login-fail", key, LOGIN_WINDOW, add=True)
        _hits("login-fail-ip", ip, LOGIN_WINDOW, add=True)
        raise AccountError(401, "邮箱或密码不对")
    _clear_hits("login-fail", key)
    return account


def issue_session(account: dict) -> str:
    payload = f"{account['id']}.{account['gen']}.{int(time.time())}"
    return f"{payload}.{_sign('session', payload)}"


def from_session(token: str | None) -> dict | None:
    if not token or not re.fullmatch(r"[0-9a-f]{24}\.[0-9]{1,9}\.[0-9]{10,12}\.[0-9a-f]{64}", token):
        return None
    payload, signature = token.rsplit(".", 1)
    account_id, gen, issued = payload.split(".")
    if not 0 <= time.time() - int(issued) <= LIFETIME or not hmac.compare_digest(_sign("session", payload), signature):
        return None
    account = load(account_id)
    return account if account and account.get("gen") == int(gen) else None


def _bump(account: dict, password: str | None = None) -> dict:
    with locked(_path(account["id"])):
        current = load(account["id"])
        if current is None:
            raise AccountError(404, "账号不存在")
        current["gen"] += 1
        if password is not None:
            current["pw"] = _hash_password(password)
        return _save(current)


def change_password(account: dict, old: str, new: str) -> dict:
    check_password(new)
    if not _verify_password(old or "", account["pw"]):
        raise AccountError(401, "原密码不对")
    return _bump(account, new)


def delete(account: dict, password: str) -> None:
    if not _verify_password(password or "", account["pw"]):
        raise AccountError(401, "密码不对")
    index = root() / "by-email" / _email_key(account["email"])
    with locked(index):
        for path in (index, _path(account["id"]), root() / f"{account['id']}.library.json"):
            path.unlink(missing_ok=True)


# ---------- 找回密码 ----------

def reset_token(account: dict, now: float | None = None) -> str:
    payload = f"{account['id']}.{int(now or time.time())}"
    return f"{payload}.{_sign('reset', payload + '|' + account['pw'])}"


def reset(token: str, password: str) -> dict:
    check_password(password)
    bad = AccountError(400, "找回链接无效或已过期，请重新申请")
    if not re.fullmatch(r"[0-9a-f]{24}\.[0-9]{10,12}\.[0-9a-f]{64}", token or ""):
        raise bad
    payload, signature = token.rsplit(".", 1)
    account_id, issued = payload.split(".")
    account = load(account_id)
    if (account is None or not 0 <= time.time() - int(issued) <= RESET_TTL
            or not hmac.compare_digest(_sign("reset", payload + "|" + account["pw"]), signature)):
        raise bad
    return _bump(account, password)


def mail_configured() -> bool:
    return bool(os.getenv("XRAY_RESEND_KEY", "").strip())


def send_mail(to: str, subject: str, text: str) -> None:
    """经 Resend 发一封纯文本邮件。测试里替换掉这个函数。"""
    response = httpx.post("https://api.resend.com/emails", timeout=15, headers={
        "Authorization": f"Bearer {os.getenv('XRAY_RESEND_KEY', '').strip()}"}, json={
        "from": os.getenv("XRAY_MAIL_FROM", "企er <no-reply@qier.asia>"), "to": [to], "subject": subject, "text": text})
    response.raise_for_status()


def forgot(email: str, ip: str, base_url: str) -> None:
    """不论邮箱有没有注册都正常返回；查到才发，发信放到后台，响应时间不暴露结果。"""
    if not mail_configured():
        raise AccountError(503, "找回邮件暂时发不出去，请稍后再试")
    email = normalize_email(email)
    if _hits("mail-ip", ip, 3600) >= MAIL_PER_IP_HOUR:
        raise AccountError(429, "找回邮件申请太频繁，请一小时后再试")
    _hits("mail-ip", ip, 3600, add=True)
    key = _email_key(email)
    if _hits("mail", key, MAIL_GAP):
        return
    _hits("mail", key, MAIL_GAP, add=True)
    account = _by_email(email)
    if account is None:
        return
    link = f"{os.getenv('XRAY_PUBLIC_URL', base_url).rstrip('/')}/xray/#/reset?t={reset_token(account)}"
    text = (f"你好：\n\n有人为企er 账号 {email} 申请了重设密码。30 分钟内打开下面的链接设置新密码：\n\n{link}\n\n"
            "如果不是你本人申请的，忽略这封邮件即可，原密码不受影响。\n\n企er")

    def deliver():
        try:
            send_mail(email, "企er：重设密码", text)
        except Exception:  # noqa: BLE001 - 发信失败只记日志，不能把原因回给申请人
            log.exception("reset mail failed")

    threading.Thread(target=deliver, daemon=True).start()


# ---------- 资料库 ----------

def library(account: dict) -> list:
    try:
        data = json.loads((root() / f"{account['id']}.library.json").read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_library(account: dict, entries: list) -> list:
    if len(entries) > LIBRARY_MAX:
        raise AccountError(413, f"资料库最多存 {LIBRARY_MAX} 个词")
    atomic_json(root() / f"{account['id']}.library.json", entries)
    return entries


# ---------- 频率记录 ----------

def _limits_path(name: str) -> Path:
    return privacy.private_dir() / "limits" / f"{name}.json"


def _hits(name: str, key: str, window: float, *, add: bool = False) -> int:
    path, now = _limits_path(name), time.time()
    with locked(path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data = {k: kept for k, v in data.items() if (kept := [t for t in v if now - t < window])}
        if add:
            data.setdefault(key, []).append(now)
            atomic_json(path, data)
        return len(data.get(key, []))


def _clear_hits(name: str, key: str) -> None:
    path = _limits_path(name)
    with locked(path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if data.pop(key, None) is not None:
            atomic_json(path, data)

