"""X-Ray 后端。

运行：cd backend && .venv\\Scripts\\python -m uvicorn app.main:app --port 8000
打开：http://localhost:8000（前端 web/）　接口文档：http://localhost:8000/docs　断网备用：/demo/
"""
import json
import hashlib
from dataclasses import asdict
import logging
import os
import queue
import threading
import time
from pathlib import Path
from uuid import uuid4
from collections.abc import Callable
from contextvars import copy_context
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, File, HTTPException, Query, Request, Response, UploadFile, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse, JSONResponse, FileResponse, HTMLResponse
from starlette.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import accounts, config, demo_prebuilt, deployment, privacy, progress, quota, runs
from app.models import PublicCase, PublicChatMessage
from app.analysis.pipeline import NoNewReviews, load_services, new_case, refresh_reviews, resolve, supplement
from app.analysis.report import onepager
from app.assistant import answer
from app.glossary import load_glossary
from app.intake import run_intake
from app.llm import LLM
from app.plain import finish_version
from app.models import (Case, CaseIn, CaseSummary, ChatIn, ChatMessage, Intake, IntakeIn, LicenseHit, OnePager,
                        ReadResult, ResolveIn, ReviewIn, ReviewList, Scenario, Source, SupplementIn, Term)
from app.readers import read_upload, MAX_UPLOAD
from app.reviews import DuplicateReview
from app.scenarios import get_scenario, load_scenarios
from app.sources.collect import collect
from app.store import CaseStore, ConflictError
from app.persistence import locked, atomic_json
from app.case_memory.store import MemoryStore
from app.sources.cache import FORCE_REFRESH
from app.sources.resolve import resolve as resolve_name

DEMO_CASES = config.DATA_DIR / "demo_cases.json"

log = logging.getLogger("xray")
svc = load_services()
llm = LLM()
store = CaseStore(config.CASES_DIR)

_workers: set[threading.Thread] = set()
_workers_lock = threading.Lock()
_stopping = threading.Event()


@asynccontextmanager
async def lifespan(application):
    _stopping.clear()
    yield
    _stopping.set()
    def drain():
        deadline = time.monotonic() + 30
        with _workers_lock:
            workers = list(_workers)
        for worker in workers:
            worker.join(timeout=max(0, deadline - time.monotonic()))
    await run_in_threadpool(drain)


def _launch(work):
    def wrapped():
        try:
            work()
        finally:
            with _workers_lock:
                _workers.discard(threading.current_thread())
    context = copy_context()
    worker = threading.Thread(target=lambda: context.run(wrapped), daemon=True)
    with _workers_lock:
        _workers.add(worker)
    worker.start()


_memory_slots = threading.BoundedSemaphore(2)
_memory_pending: set[tuple[str, str, int]] = set()
_memory_lock = threading.Lock()


def _persist_case(case: Case) -> Case:
    """One post-persistence hook for every new version, including demo copies."""
    saved = store.save(case)
    if not config.CASE_MEMORY_ENABLED or _stopping.is_set() or not saved.owner_id:
        return saved
    owner = privacy.identity()
    if saved.owner_id != owner:
        raise PermissionError("Cannot build another guest's memory")
    key = (owner, saved.id, saved.current)
    with _memory_lock:
        if key in _memory_pending or not _memory_slots.acquire(blocking=False):
            return saved  # Lazy read can safely rebuild if the bounded worker is busy.
        _memory_pending.add(key)
    snapshot = saved.model_copy(deep=True)
    def work():
        try:
            MemoryStore().get_or_build(snapshot, snapshot.current, owner)
        except Exception as error:
            log.warning("case_memory_build_failed error_type=%s", type(error).__name__)
        finally:
            with _memory_lock:
                _memory_pending.discard(key)
            _memory_slots.release()
    try:
        _launch(work)
    except Exception as error:
        with _memory_lock:
            _memory_pending.discard(key)
        _memory_slots.release()
        log.warning("case_memory_schedule_failed error_type=%s", type(error).__name__)
    return saved


app = FastAPI(title="X-Ray 透视·真相", version="0.2.0", lifespan=lifespan)


@app.exception_handler(ConflictError)
async def conflict_handler(request, error):
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.exception_handler(accounts.AccountError)
async def account_error_handler(request, error):
    return JSONResponse(status_code=error.status, content={"detail": error.detail})
RUNS_DIR = Path(os.getenv("XRAY_RUNS_DIR", config.DATA_DIR / "runs"))
_active_runs: set[str] = set()
_active_lock = threading.Lock()
_run_slots = threading.BoundedSemaphore(max(1, int(os.getenv("XRAY_MAX_RUNS", "4"))))


def _reserve_run():
    if _stopping.is_set():
        raise HTTPException(status_code=503, detail="服务正在停止，请稍后重试")
    if not _run_slots.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="当前研究任务已满，请稍后重试", headers={"Retry-After": "5"})


def _inline(work):
    _reserve_run()
    try:
        return work()
    finally:
        _run_slots.release()
# 前端由本服务同源提供；放开跨域只是方便有人单独起前端调试
app.add_middleware(CORSMiddleware, allow_origins=privacy.allowed_origins(), allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type", "Idempotency-Key"])
app.add_middleware(privacy.GuestPrivacyMiddleware)


def _case(case_id: str) -> Case:
    case = store.get(case_id)
    if case is None or case.owner_id != privacy.identity():
        raise HTTPException(status_code=404, detail="案卷不存在")
    return case


@app.get("/api/health")
def health() -> dict:
    lists = {rid: {"title": i.title, "count": i.meta.get("count", len(i)), "as_of": i.meta.get("as_of")}
             for rid, i in svc.registries.items()}
    return {"ok": True, "licensed_count": len(svc.licenses), "licensed_as_of": svc.licenses.meta["as_of"],
            "registry_as_of": svc.registry.as_of, "official_lists": lists, "evidence_packs": svc.packs.names(),
            "commercial": svc.commercial.status() if svc.commercial else {"configured": False},
            "assistant_context": {"mode": config.ASSISTANT_CONTEXT_MODE,
                                  "memory_enabled": config.CASE_MEMORY_ENABLED},
            "web_discovery": {"enabled": config.WEB_DISCOVERY_ENABLED,
                              "search_configured": svc.web is not None,
                              "max_queries": config.WEB_DISCOVERY_QUERIES,
                              "max_rounds": config.WEB_DISCOVERY_ROUNDS,
                              "total_seconds": config.WEB_DISCOVERY_SECONDS},
            "llm": llm.status(), "deployment": deployment.status()}


@app.get("/api/session")
def guest_session() -> dict:
    account, guest = privacy.ACCOUNT.get(), privacy.GUEST.get()
    out = {"private": True, "identity": "account" if account else "browser_guest", "cross_device": bool(account),
           "account": accounts.public(account), "mail": accounts.mail_configured(),
           "quota": quota.status(privacy.identity(), account),
           "notice": "材料、案卷和聊天只有登录这个账号才能看到；换设备登录同一账号即可找回。只有主动提交的评价会公开。"
           if account else "材料、案卷和聊天仅此浏览器可见；清除浏览器数据后不能自动恢复，登录后可以换设备找回。只有主动提交的评价会公开。"}
    if account:
        out["guest_cases"] = len(store.list(owner_id=guest)) if guest else 0
    return out


# ---------- 账号：可选，登录了换设备也能找回 ----------

class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


def _set_session(request: Request, response: Response, account: dict) -> dict:
    secure = request.url.scheme == "https"
    response.set_cookie(accounts.cookie_name(secure), accounts.issue_session(account), max_age=accounts.LIFETIME,
                        path="/", httponly=True, samesite="lax", secure=secure)
    guest = privacy.GUEST.get()
    return {"account": accounts.public(account), "guest_cases": len(store.list(owner_id=guest)) if guest else 0}


def _account() -> dict:
    account = privacy.ACCOUNT.get()
    if account is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return account


@app.post("/api/auth/register")
def register(body: Credentials, request: Request, response: Response) -> dict:
    return _set_session(request, response, accounts.register(body.email, body.password))


@app.post("/api/auth/login")
def login(body: Credentials, request: Request, response: Response) -> dict:
    return _set_session(request, response, accounts.login(body.email, body.password, privacy.CLIENT_IP.get()))


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict:
    """退出时连匿名身份一起换掉：下一个人用这台电脑，看不到未登录时留下的东西。"""
    secure = request.url.scheme == "https"
    response.delete_cookie(accounts.cookie_name(secure), path="/", secure=secure, httponly=True, samesite="lax")
    response.set_cookie(privacy.SECURE_COOKIE if secure else privacy.COOKIE, privacy.issue(), max_age=privacy.LIFETIME,
                        path="/", httponly=True, samesite="lax", secure=secure)
    return {"ok": True}


@app.post("/api/auth/merge")
def merge_guest() -> dict:
    """用户确认后，把这个浏览器未登录时的案卷和研究任务并入账号。"""
    owner, guest = accounts.owner(_account()), privacy.GUEST.get()
    if not guest or guest == owner:
        return {"moved": 0}
    runs.reassign(RUNS_DIR, guest, owner)
    return {"moved": store.reassign(guest, owner)}


class PasswordChange(BaseModel):
    old: str = Field(max_length=128)
    new: str = Field(max_length=128)


@app.post("/api/auth/password")
def change_password(body: PasswordChange, request: Request, response: Response) -> dict:
    return _set_session(request, response, accounts.change_password(_account(), body.old, body.new))


class ForgotIn(BaseModel):
    email: str = Field(max_length=254)


@app.post("/api/auth/forgot")
def forgot_password(body: ForgotIn, request: Request) -> dict:
    accounts.forgot(body.email, privacy.CLIENT_IP.get(), str(request.base_url))
    return {"ok": True, "message": "如果这个邮箱注册过，重设密码的邮件已经发出，30 分钟内有效。没收到请看看垃圾邮件。"}


class ResetIn(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(max_length=128)


@app.post("/api/auth/reset")
def reset_password(body: ResetIn, request: Request, response: Response) -> dict:
    return _set_session(request, response, accounts.reset(body.token, body.password))


class DeleteIn(BaseModel):
    password: str = Field(max_length=128)


@app.post("/api/auth/delete")
def delete_account(body: DeleteIn, request: Request, response: Response) -> dict:
    """注销：删掉账号和资料库。名下案卷不再有人能打开。"""
    accounts.delete(_account(), body.password)
    secure = request.url.scheme == "https"
    response.delete_cookie(accounts.cookie_name(secure), path="/", secure=secure, httponly=True, samesite="lax")
    return {"ok": True}


@app.get("/api/me/library")
def get_library() -> list[dict]:
    return accounts.library(_account())


class LibrarySeen(BaseModel):
    caseId: str = Field(max_length=40)
    version: int | None = None
    company: str = Field("", max_length=120)


class LibraryEntry(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    term: str = Field(max_length=80)
    plain: str = Field("", max_length=2000)
    why: str = Field("", max_length=2000)
    basis: str = Field("", max_length=300)
    origin: str | None = Field(None, max_length=20)
    savedAt: str = Field("", max_length=40)
    seen: list[LibrarySeen] = Field(default_factory=list, max_length=50)


@app.put("/api/me/library")
def put_library(entries: list[LibraryEntry] = Body(..., max_length=accounts.LIBRARY_MAX)) -> list[dict]:
    return accounts.save_library(_account(), [e.model_dump() for e in entries])


def _metered(demo: bool, start):
    """新建或补充一次研究就记一次；预制示例的回放不记。启动失败退回。"""
    keys = [] if demo else quota.charge(privacy.identity(), privacy.ACCOUNT.get(), privacy.CLIENT_IP.get())
    try:
        return start()
    except BaseException:
        quota.refund(keys)
        raise


@app.get("/api/sources")
def sources() -> list[Source]:
    return list(svc.sources.values())


@app.get("/api/scenarios")
def scenarios() -> list[Scenario]:
    return list(load_scenarios().values())


@app.get("/api/glossary")
def glossary() -> list[Term]:
    return list(load_glossary())


@app.post("/api/intake")
def intake(body: IntakeIn) -> Intake:
    return run_intake(body.need, llm, company=body.company_name)


@app.post("/api/read")
async def read_file(file: UploadFile = File(...)) -> ReadResult:
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="文件超过 10MB")
    return await run_in_threadpool(read_upload, file.filename or "", data, llm)


@app.get("/api/licenses/check")
def check_license(name: str = Query(min_length=2, description="机构全称；输入简称会返回候选")) -> LicenseHit:
    return svc.licenses.lookup(name)


@app.get("/api/companies/resolve")
def resolve_company(q: str = Query(min_length=1, max_length=80, description="用户输入的公司名，简称也行")) -> dict:
    """开查之前把名字定成全称：精确对上就返回全称；简称返回候选让用户选，不替用户挑。"""
    return asdict(resolve_name(q, svc))


@app.get("/api/companies/profile")
def company_profile(name: str = Query(min_length=2)) -> dict:
    c = collect(name, svc)
    return {"covered": c.company is not None, "company": c.company, "license": c.license, "amac": c.amac,
            "records": c.records}


def _intake(text: str, scenario: str | None, company: str) -> Intake:
    progress.start("intake")
    info = run_intake(text, llm, scenario=scenario, company=company)
    progress.done("intake", text=progress.intake_text(info))
    return info


def _create(body: CaseIn) -> Case:
    if (bundle := demo_prebuilt.for_create(body)) is not None:   # 示例：交出预制好的案卷，不联网
        return _persist_case(demo_prebuilt.start_case(bundle, privacy.identity()))
    info = _intake(body.need, body.scenario, body.company_name)
    token = FORCE_REFRESH.set(body.refresh_sources)
    try:
        case = finish_version(new_case(body, info, svc), llm)
        case.owner_id = privacy.identity()
        return _persist_case(case)
    finally:
        FORCE_REFRESH.reset(token)


def _supplement(case: Case, body: SupplementIn) -> Case:
    if (hit := demo_prebuilt.for_supplement(case, body)) is not None:   # 示例按顺序补充：交出预制的下一版
        return _persist_case(demo_prebuilt.next_case(case, *hit))
    info = _intake(body.text, body.scenario, case.case.company_name) if body.kind == "need" else None
    token = FORCE_REFRESH.set(body.refresh_sources)
    try:
        return _persist_case(finish_version(supplement(case, body, info, svc), llm))
    finally:
        FORCE_REFRESH.reset(token)


def _stream(first: dict, work: Callable[[], Case]) -> StreamingResponse:
    """边做边发进度：一行一个 JSON（NDJSON）。begin → 各步 start/done → 最后一行 case（整个案卷）或 error。

    t 是从收到请求起的秒数。活在后台线程里做，客户端中途断开也会做完、存好案卷。
    """
    _reserve_run()
    events: queue.Queue = queue.Queue(maxsize=128)
    disconnected = threading.Event()
    t0 = time.monotonic()

    def put(event: dict) -> None:
        if disconnected.is_set():
            return
        try:
            events.put_nowait({**event, "t": round(time.monotonic() - t0, 2)})
        except queue.Full:
            # Progress may be coalesced; the final case/error must remain observable.
            events.get_nowait()
            events.put_nowait({**event, "t": round(time.monotonic() - t0, 2)})

    def run() -> None:
        try:
            with progress.reporting(put):
                case = work()
            put({"type": "case", "case": PublicCase.model_validate(case.model_dump()).model_dump(mode="json")})
        except HTTPException as e:
            put({"type": "error", "status": e.status_code, "message": str(e.detail)})
        except ConflictError as e:
            put({"type": "error", "status": 409, "message": str(e)})
        except Exception:  # noqa: BLE001 —— 出错要告诉前端，不能让流悄悄断掉
            log.exception("stream failed")
            put({"type": "error", "status": 500, "message": "生成失败，请重试；多次失败请查看后端日志"})
        finally:
            _run_slots.release()
            if events.full():
                events.get_nowait()
            events.put_nowait(None)

    put(first)
    _launch(run)

    def lines():
        try:
            while (event := events.get()) is not None:
                yield json.dumps(event, ensure_ascii=False) + "\n"
        finally:
            disconnected.set()

    return StreamingResponse(lines(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _start_run(first: dict, work: Callable[[], Case], run_id: str | None = None,
               *, original_input: dict | None = None) -> dict:
    """Launch a case build and retain progress independently of the browser connection."""
    run_id = run_id or uuid4().hex[:24]
    _reserve_run()
    directory = RUNS_DIR
    stopped = threading.Event()
    started = time.monotonic()

    def put(event: dict) -> None:
        runs.append(directory, run_id, {**event, "t": round(time.monotonic() - started, 2)})

    with _active_lock:  # 先登记再写第一条，免得查询时看到"没在跑、也没结束"
        _active_runs.add(run_id)
    try:
        if original_input is not None:
            runs.save_input(directory, run_id, original_input)
        runs.set_owner(directory, run_id, privacy.identity())
        runs.touch(directory, run_id)
        put(first)
    except Exception:
        with _active_lock:
            _active_runs.discard(run_id)
        _run_slots.release()
        raise

    def heartbeat():
        while not stopped.wait(5):
            try:
                runs.touch(directory, run_id)
            except OSError:
                log.exception("run heartbeat failed")

    def run() -> None:
        try:
            with progress.reporting(put):
                case = work()
            put({"type": "complete", "case_id": case.id, "version": case.current})
        except ConflictError as e:
            put({"type": "error", "status": 409, "message": str(e)})
        except Exception:  # noqa: BLE001 - raw provider errors stay in server logs
            log.exception("run failed")
            put({"type": "error", "message": "生成失败，请重试；如页面中断，先到案卷列表确认结果"})
        finally:
            stopped.set()
            _run_slots.release()
            runs.touch(directory, run_id, finished=True)
            with _active_lock:
                _active_runs.discard(run_id)

    threading.Thread(target=heartbeat, daemon=True).start()
    _launch(run)
    return {"run_id": run_id, "status": "running"}


def _idempotent_run(key: str | None, scope: str, body: BaseModel, start):
    if not key:
        return start(None)
    digest = hashlib.sha256((privacy.identity() + "|" + scope + "|" + key).encode()).hexdigest()
    fingerprint = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    path = RUNS_DIR / "requests" / f"{digest}.json"
    with locked(path):
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved["fingerprint"] != fingerprint:
                raise ConflictError("相同 Idempotency-Key 的请求内容不同")
            return saved["result"]
        result = {"run_id": uuid4().hex[:24], "status": "running"}
        runs.set_owner(RUNS_DIR, result["run_id"], privacy.identity())
        runs.append(RUNS_DIR, result["run_id"], {"type": "queued"})
        atomic_json(path, {"fingerprint": fingerprint, "result": result})
        try:
            return start(result["run_id"])
        except Exception:
            runs.append(RUNS_DIR, result["run_id"], {"type": "error", "message": "任务未启动，请稍后使用新的请求键重试"})
            raise


@app.post("/api/runs", status_code=202)
def create_run(body: CaseIn, idempotency_key: str | None = Header(None, max_length=128)) -> dict:
    demo = demo_prebuilt.for_create(body) is not None
    return _idempotent_run(idempotency_key, "create", body, lambda rid: _metered(demo, lambda:
                           _start_run(progress.begin("create", body.company_name, intake=True), lambda: _create(body), rid,
                                      original_input={"kind": "create", "body": body.model_dump(mode="json")})))


@app.post("/api/cases/{case_id}/runs", status_code=202)
def supplement_run(case_id: str, body: SupplementIn, idempotency_key: str | None = Header(None, max_length=128)) -> dict:
    case = _case(case_id)
    demo = demo_prebuilt.for_supplement(case, body) is not None
    return _idempotent_run(idempotency_key, f"supplement:{case_id}", body, lambda rid: _metered(demo, lambda:
                          _start_run(progress.begin("supplement", case.case.company_name, intake=body.kind == "need"),
                                     lambda: _supplement(case, body), rid,
                                     original_input={"kind": "supplement", "case_id": case_id, "body": body.model_dump(mode="json")})))


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, after: int = Query(0, ge=0)) -> dict:
    if not runs.owned_by(RUNS_DIR, run_id, privacy.identity()):
        raise HTTPException(status_code=404, detail="研究任务不存在或不属于此浏览器")
    try:
        all_events = runs.events(RUNS_DIR, run_id)
    except ValueError:
        all_events = None
    if all_events is None:
        raise HTTPException(status_code=404, detail="研究任务不存在")
    terminal = next((e for e in reversed(all_events) if e.get("type") in ("complete", "error")), None)
    with _active_lock:
        active = runs.active(RUNS_DIR, run_id)
    status = ("complete" if terminal["type"] == "complete" else "error") if terminal else ("running" if active else "interrupted")
    return {"run_id": run_id, "status": status, "case_id": terminal.get("case_id") if terminal else None,
            "version": terminal.get("version") if terminal else None,
            "input": runs.read_input(RUNS_DIR, run_id) if after == 0 else None,
            "events": all_events[after:], "next": len(all_events)}


@app.post("/api/cases", response_model=PublicCase)
def create_case(body: CaseIn) -> Case:
    return _metered(demo_prebuilt.for_create(body) is not None, lambda: _inline(lambda: _create(body)))


@app.post("/api/cases/stream")
def create_case_stream(body: CaseIn) -> StreamingResponse:
    """同 /api/cases，但边查边发进度，给等待动画用。事件格式见 docs/progress-events.md。"""
    return _metered(demo_prebuilt.for_create(body) is not None,
                    lambda: _stream(progress.begin("create", body.company_name, intake=True), lambda: _create(body)))


@app.get("/api/cases")
def list_cases(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)) -> list[CaseSummary]:
    return store.list(limit=limit, offset=offset, owner_id=privacy.identity())


@app.get("/api/cases/{case_id}/versions/{version_no}")
def get_version(case_id: str, version_no: int):
    case = _case(case_id)
    version = next((v for v in case.versions if v.no == version_no), None)
    if version is None:
        raise HTTPException(status_code=404, detail="没有这个版本")
    return {"id": case.id, "revision": case.revision, "version": version,
            "raw": [r for r in case.raw if r.id in version.raw_ids], "sources": version.sources or case.sources}


@app.get("/api/cases/{case_id}", response_model=PublicCase)
def get_case(case_id: str) -> Case:
    return _case(case_id)


@app.post("/api/cases/{case_id}/supplements", response_model=PublicCase)
def add_supplement(case_id: str, body: SupplementIn) -> Case:
    case = _case(case_id)
    return _metered(demo_prebuilt.for_supplement(case, body) is not None, lambda: _inline(lambda: _supplement(case, body)))


@app.post("/api/cases/{case_id}/supplements/stream")
def add_supplement_stream(case_id: str, body: SupplementIn) -> StreamingResponse:
    """同 /supplements，但边查边发进度。案卷不存在照常回 404，不开流。"""
    case = _case(case_id)
    return _metered(demo_prebuilt.for_supplement(case, body) is not None,
                    lambda: _stream(progress.begin("supplement", case.case.company_name, intake=body.kind == "need"),
                                    lambda: _supplement(case, body)))


@app.post("/api/cases/{case_id}/resolve", response_model=PublicCase)
def resolve_judgment(case_id: str, body: ResolveIn) -> Case:
    """人对某条判断下结论（已澄清 / 已撤回 / 继续查）。出一版新案卷，旧版留着。"""
    case = _case(case_id)
    try:
        return _persist_case(resolve(case, body))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"案卷里没有这条判断：{body.judgment_id}") from None


@app.post("/api/cases/{case_id}/reviews", response_model=PublicCase)
def refresh_case_reviews(case_id: str) -> Case:
    """把这家公司最新的用户评价放进案卷，出一版新报告。评价没变就不出。"""
    case = _case(case_id)
    try:
        return _persist_case(finish_version(refresh_reviews(case, svc), llm))
    except NoNewReviews:
        raise HTTPException(status_code=409, detail="没有新评价：这一版报告里已经是最新的评价") from None


# ---------- 用户评价：按公司存，别人说的，未核实 ----------

@app.get("/api/reviews")
def list_reviews(company: str = Query(..., min_length=2, max_length=80),
                 author: str | None = Query(None, description="浏览器的匿名编号，用来标出哪条是自己写的")) -> ReviewList:
    return svc.reviews.listing(company.strip(), privacy.OWNER.get())


@app.post("/api/reviews")
def add_review(body: ReviewIn) -> ReviewList:
    try:
        return svc.reviews.add(body.model_copy(update={"author": privacy.identity()}))
    except DuplicateReview:
        raise HTTPException(status_code=409, detail="你已经给这家公司写过一条评价了") from None


@app.post("/api/cases/{case_id}/chat", response_model=PublicChatMessage)
def chat(case_id: str, body: ChatIn, idempotency_key: str | None = Header(None, min_length=1, max_length=128)) -> ChatMessage:
    case = _case(case_id)
    path = _chat_request_path(case_id, idempotency_key) if idempotency_key else None
    fingerprint = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    if path:
        with locked(path):
            if path.exists():
                saved = json.loads(path.read_text(encoding="utf-8"))
                if saved["fingerprint"] != fingerprint:
                    raise HTTPException(status_code=409, detail="同一问答请求标识不能用于不同问题")
                previous = next((m for m in case.chat if m.role == "assistant" and m.request_id == idempotency_key), None)
                if previous:
                    return previous
                raise HTTPException(status_code=409, detail="这条提问已提交，请恢复结果；不要重复发送。")
            atomic_json(path, {"fingerprint": fingerprint, "status": "running", "started": time.time()})
    try:
        reply = answer(case, body, llm, version_no=body.version)
        reply.request_id = idempotency_key
        store.append_chat(case_id, [ChatMessage(role="user", text=body.text, refs=body.refs, version=reply.version,
                                               request_id=idempotency_key, created_at=reply.created_at), reply])
        if path:
            atomic_json(path, {"fingerprint": fingerprint, "status": "complete", "started": time.time()})
        return reply
    except Exception:
        if path:
            atomic_json(path, {"fingerprint": fingerprint, "status": "failed", "started": time.time()})
        raise


def _chat_request_path(case_id: str, key: str) -> Path:
    digest = hashlib.sha256(f"{privacy.identity()}|{case_id}|{key}".encode()).hexdigest()
    return store.dir / "chat-requests" / f"{digest}.json"


@app.get("/api/cases/{case_id}/chat/requests/{request_key}")
def chat_request_status(case_id: str, request_key: str) -> dict:
    case = _case(case_id)
    if not 1 <= len(request_key) <= 128:
        raise HTTPException(status_code=404, detail="没有这条提问")
    path = _chat_request_path(case_id, request_key)
    if not path.exists():
        raise HTTPException(status_code=404, detail="没有这条提问")
    # Reading the case first recovers the save-before-response interruption window.
    previous = next((m for m in case.chat if m.role == "assistant" and m.request_id == request_key), None)
    if previous:
        return {"status": "complete", "reply": PublicChatMessage.model_validate(previous.model_dump()).model_dump()}
    saved = json.loads(path.read_text(encoding="utf-8"))
    status = saved["status"]
    if status == "running" and time.time() - saved["started"] > config.CHAT_TIMEOUT + config.LLM_TIMEOUT + 30:
        status = "interrupted"
    return {"status": status, "reply": None}


@app.get("/api/cases/{case_id}/onepager")
def get_onepager(case_id: str, audience: str = Query("family", pattern="^(family|teller)$"),
                 version: int | None = None) -> OnePager:
    case = _case(case_id)
    v = next((x for x in case.versions if x.no == version), None) if version else case.versions[-1]
    if v is None:
        raise HTTPException(status_code=404, detail="没有这个版本")
    return onepager(company_name=case.case.company_name, for_whom=v.for_whom, amount=v.amount,
                    scenario=get_scenario(v.scenario), assertions=v.assertions, missing=v.missing, signals=v.signals,
                    questions=v.questions, sources=v.sources or case.sources, audience=audience)


# ---------- 演示案例 ----------

class DemoCase(BaseModel):
    id: str
    label: str
    real: bool
    ready: bool
    note: str | None = None
    input: CaseIn | None = None
    supplements: list[SupplementIn] = []


def _demo_cases() -> list[DemoCase]:
    raw = json.loads(DEMO_CASES.read_text(encoding="utf-8"))["cases"]
    out = []
    for d in raw:
        inp, sups = None, []
        if d.get("ready"):
            material = (config.FIXTURES_DIR / d["material_file"]).read_text(encoding="utf-8") if d.get("material_file") else None
            inp = CaseIn(**d["input"], material_text=material, material_title=d.get("material_title"))
            for s in d.get("supplements", []):
                text = (config.FIXTURES_DIR / s["file"]).read_text(encoding="utf-8") if s.get("file") else s["text"]
                sups.append(SupplementIn(kind=s["kind"], text=text, title=s.get("title")))
        out.append(DemoCase(id=d["id"], label=d["label"], real=d["real"], ready=d.get("ready", False),
                            note=d.get("note"), input=inp, supplements=sups))
    return out


@app.get("/api/demo/cases")
def demo_cases() -> list[DemoCase]:
    return _demo_cases()


@app.get("/api/demo")
def demo_case(case: str | None = Query(None, description="A / B / C；不填取第一个准备好的")) -> DemoCase:
    cases = _demo_cases()
    pick = next((c for c in cases if c.id == case), None) if case else next((c for c in cases if c.ready), None)
    if pick is None:
        raise HTTPException(status_code=404, detail="没有这个演示案例")
    if not pick.ready:
        raise HTTPException(status_code=409, detail=f"演示案例 {pick.id} 还没准备好：{pick.note or ''}")
    return pick


# ---------- 静态页面：放在最后，避免盖住 /api ----------

research_assets = config.REPO_DIR / "research-room" / "public"
home_build = config.REPO_DIR / "research-room" / "home-dist"


@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def research_home():
    entry = home_build / "index.html"
    if entry.is_file():
        return FileResponse(entry, headers={"Cache-Control": "no-cache"})
    return HTMLResponse(
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<title>研究室尚未构建</title><h1>研究室首页尚未构建</h1>'
        '<p>请在 research-room 目录执行 npm install 和 npm run build:home，然后刷新。</p>'
        '<p><a href="/xray/#/cases">查看已有案卷</a></p></html>', status_code=503)


app.mount("/office", StaticFiles(directory=home_build, check_dir=False), name="office")
if research_assets.exists():
    app.mount("/research-assets", StaticFiles(directory=research_assets), name="research-assets")
if config.DEMO_DIR.exists():
    app.mount("/demo", StaticFiles(directory=config.DEMO_DIR, html=True), name="demo")
if config.WEB_DIR.exists():
    app.mount("/xray", StaticFiles(directory=config.WEB_DIR, html=True), name="reports")
    # Keep old direct asset URLs working; the root route above owns the homepage.
    app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
