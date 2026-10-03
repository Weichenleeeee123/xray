"""每天新建研究的次数。一次真实研究要调商业接口和模型，花的是真钱。

- 登录了按账号算；没登录按匿名浏览器算，同时按 IP 设一个宽松的上限（换 cookie 就能绕开匿名额度）。
- IP 上限只管匿名：路演现场大家共用一个出口，撞了上限登录就能继续。
- 预制示例的回放不计数，由调用方判断。按北京时间的自然日计。数值为 0 表示不限。
"""
import json
import os
from datetime import datetime, timedelta, timezone

from app import privacy
from app.accounts import AccountError
from app.persistence import atomic_json, locked

BEIJING = timezone(timedelta(hours=8))


def limits() -> dict[str, int]:
    return {"guest": int(os.getenv("XRAY_QUOTA_GUEST", "5")), "ip": int(os.getenv("XRAY_QUOTA_IP", "40")),
            "account": int(os.getenv("XRAY_QUOTA_ACCOUNT", "30"))}


def _path():
    return privacy.private_dir() / "usage" / f"{datetime.now(BEIJING).date().isoformat()}.json"


def _read(path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _keys(owner: str, account: dict | None, ip: str) -> list[tuple[str, int, str]]:
    cap = limits()
    if account:
        return [(f"a:{account['id']}", cap["account"], f"今天的 {cap['account']} 次研究已经用完，明天再来")]
    keys = [(f"g:{owner}", cap["guest"], f"未登录每天可以新建 {cap['guest']} 次研究，今天已经用完；登录后每天 {cap['account']} 次")]
    if ip:
        keys.append((f"ip:{ip}", cap["ip"], "这个网络今天的研究次数已经用完；登录后可以继续"))
    return keys


def status(owner: str, account: dict | None) -> dict:
    key, cap, _ = _keys(owner, account, "")[0]
    return {"used": _read(_path()).get(key, 0), "limit": cap or None}


def charge(owner: str, account: dict | None, ip: str) -> list[str]:
    """记一次；超了就拒绝，什么都不记。返回记过的键，启动失败时用来退回。"""
    path, keys = _path(), _keys(owner, account, ip)
    with locked(path):
        data = _read(path)
        for key, cap, message in keys:
            if cap and data.get(key, 0) >= cap:
                raise AccountError(429, message)
        charged = [key for key, cap, _ in keys if cap]
        for key in charged:
            data[key] = data.get(key, 0) + 1
        if charged:
            atomic_json(path, data)
    return charged


def refund(keys: list[str]) -> None:
    if not keys:
        return
    path = _path()
    with locked(path):
        data = _read(path)
        for key in keys:
            if data.get(key, 0) > 0:
                data[key] -= 1
        atomic_json(path, data)
