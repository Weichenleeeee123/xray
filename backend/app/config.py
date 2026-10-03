import os
import math
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
FIXTURES_DIR = DATA_DIR / "fixtures"
EVIDENCE_DIR = DATA_DIR / "evidence_packs"
LICENSE_CSV = DATA_DIR / "licensed_institutions.csv"
LICENSE_META = DATA_DIR / "licensed_institutions.meta.json"
SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"
WEB_DIR = REPO_DIR / "web"
DEMO_DIR = REPO_DIR / "demo"


def _load_env(path: Path) -> None:
    """读 backend/.env（KEY=VALUE 一行一个），已有的环境变量优先。不引入 python-dotenv。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env(BASE_DIR / ".env")

# 运行时数据，git 忽略；测试时用环境变量指到临时目录
CASES_DIR = Path(os.getenv("XRAY_CASES_DIR", DATA_DIR / "cases"))
# 用户评价：按公司存；演示评价在 fixtures/reviews.json（只读）
REVIEWS_DIR = Path(os.getenv("XRAY_REVIEWS_DIR", DATA_DIR / "reviews"))
CACHE_DIR = Path(os.getenv("XRAY_CACHE_DIR", DATA_DIR / "cache"))
# 名单里查到的私募管理人，再取一次中基协公示详情页（公开页面，没有验证码）；测试里关掉
AMAC_DETAIL = os.getenv("XRAY_AMAC_DETAIL", "1") == "1"

# 模型网关（比赛的 Tokendance，OpenAI 兼容）。没配 Key 时所有功能退回规则和模板。
LLM_BASE_URL = os.getenv("TOKENDANCE_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.getenv("TOKENDANCE_API_KEY", "")
LLM_MODEL = os.getenv("TOKENDANCE_MODEL", "")
LLM_VISION_MODEL = os.getenv("TOKENDANCE_VISION_MODEL", "") or LLM_MODEL
# 网关是否支持 response_format={"type": "json_object"}，B1 测完再打开
LLM_JSON_MODE = os.getenv("TOKENDANCE_JSON_MODE", "0") == "1"
LLM_TIMEOUT = float(os.getenv("TOKENDANCE_TIMEOUT", "45"))
CHAT_TIMEOUT = float(os.getenv("XRAY_CHAT_TIMEOUT", "60"))
# 可回退的模型辅助阶段：首个请求和 JSON 修复共用预算，不限制事实采集或 OCR。
INTAKE_TIMEOUT = float(os.getenv("XRAY_INTAKE_TIMEOUT", "8"))
PLAIN_TIMEOUT = float(os.getenv("XRAY_PLAIN_TIMEOUT", "12"))
ASSISTANT_CONTEXT_MODE = os.getenv("XRAY_ASSISTANT_CONTEXT_MODE", "full")
CASE_MEMORY_ENABLED = os.getenv("XRAY_CASE_MEMORY_ENABLED", "0") == "1"
CASE_MEMORY_DIR = Path(os.getenv("XRAY_CASE_MEMORY_DIR", CASES_DIR.parent / "case_memory"))
ASSISTANT_CONTEXT_CHARS = int(os.getenv("XRAY_ASSISTANT_CONTEXT_CHARS", "240000"))
ASSISTANT_EVIDENCE_CHARS = int(os.getenv("XRAY_ASSISTANT_EVIDENCE_CHARS", "70000"))
# live：调用网关并录下响应，失败时回放录音；replay：只回放；off：不调用
LLM_MODE = os.getenv("XRAY_LLM_MODE", "live")

# Public discovery only; no private input is sent to search providers.
WEB_DISCOVERY_ENABLED = os.getenv("XRAY_WEB_DISCOVERY", "1") == "1"
WEB_DISCOVERY_QUERIES = int(os.getenv("XRAY_WEB_DISCOVERY_QUERIES", "10"))
WEB_DISCOVERY_ROUNDS = int(os.getenv("XRAY_WEB_DISCOVERY_ROUNDS", "2"))
WEB_DISCOVERY_WORKERS = int(os.getenv("XRAY_WEB_DISCOVERY_WORKERS", "3"))
WEB_DISCOVERY_SECONDS = float(os.getenv("XRAY_WEB_DISCOVERY_SECONDS", "35"))
WEB_DISCOVERY_READS = int(os.getenv("XRAY_WEB_DISCOVERY_READS", "8"))
WEB_DISCOVERY_HOST_READS = int(os.getenv("XRAY_WEB_DISCOVERY_HOST_READS", "3"))
WEB_DISCOVERY_SEARCH_TIMEOUT = float(os.getenv("XRAY_WEB_DISCOVERY_SEARCH_TIMEOUT", "10"))
WEB_DISCOVERY_READ_TIMEOUT = float(os.getenv("XRAY_WEB_DISCOVERY_READ_TIMEOUT", "8"))
WEB_DISCOVERY_PAGE_CHARS = int(os.getenv("XRAY_WEB_DISCOVERY_PAGE_CHARS", "12000"))
WEB_DISCOVERY_LLM = os.getenv("XRAY_WEB_DISCOVERY_LLM", "1") == "1"

# 演示参数：一年期定期存款参考利率。正式版应按实际挂牌利率更新，并在界面标注来源。
REF_DEPOSIT_RATE = float(os.getenv("XRAY_REF_DEPOSIT_RATE", "0.011"))
# 宣称收益超过定存多少倍时标为"要留意"
HIGH_RETURN_RATIO = 3.0
# 实缴低于认缴的这个比例，"注册资本 X 万"的说法算误导
LOW_PAID_RATIO = 0.1
# 成立不满多少个月，标为"成立时间短"
YOUNG_COMPANY_MONTHS = 24


def validate_settings():
    errors = []
    for name, value in (("TOKENDANCE_TIMEOUT", LLM_TIMEOUT), ("XRAY_CHAT_TIMEOUT", CHAT_TIMEOUT),
                        ("XRAY_INTAKE_TIMEOUT", INTAKE_TIMEOUT), ("XRAY_PLAIN_TIMEOUT", PLAIN_TIMEOUT),
                        ("XRAY_REF_DEPOSIT_RATE", REF_DEPOSIT_RATE)):
        if not math.isfinite(value) or value <= 0:
            errors.append(f"{name} 必须是有限正数")
    if LLM_MODE not in ("live", "replay", "off"):
        errors.append("XRAY_LLM_MODE 必须为 live/replay/off")
    if ASSISTANT_CONTEXT_MODE not in ("full", "shadow", "selective"):
        errors.append("XRAY_ASSISTANT_CONTEXT_MODE 必须为 full/shadow/selective")
    if ASSISTANT_CONTEXT_CHARS < 2000 or not 1000 <= ASSISTANT_EVIDENCE_CHARS < ASSISTANT_CONTEXT_CHARS:
        errors.append("问答上下文预算必须大于证据预算，且均为正整数")
    for name, value, low, high in (("QUERIES", WEB_DISCOVERY_QUERIES, 1, 30),
                                 ("ROUNDS", WEB_DISCOVERY_ROUNDS, 1, 3),
                                 ("WORKERS", WEB_DISCOVERY_WORKERS, 1, 6),
                                 ("READS", WEB_DISCOVERY_READS, 0, 30),
                                 ("HOST_READS", WEB_DISCOVERY_HOST_READS, 1, 10),
                                 ("PAGE_CHARS", WEB_DISCOVERY_PAGE_CHARS, 500, 50000)):
        if not low <= value <= high:
            errors.append(f"XRAY_WEB_DISCOVERY_{name} 必须在 {low} 到 {high} 之间")
    if not math.isfinite(WEB_DISCOVERY_SECONDS) or not 1 <= WEB_DISCOVERY_SECONDS <= 120:
        errors.append("XRAY_WEB_DISCOVERY_SECONDS 必须在 1 到 120 秒之间")
    for name, value in (("SEARCH_TIMEOUT", WEB_DISCOVERY_SEARCH_TIMEOUT), ("READ_TIMEOUT", WEB_DISCOVERY_READ_TIMEOUT)):
        if not math.isfinite(value) or not 1 <= value <= 30:
            errors.append(f"XRAY_WEB_DISCOVERY_{name} 必须在 1 到 30 秒之间")
    if os.getenv("XRAY_COMMERCIAL", "").strip().lower() not in ("", "qcc", "qcc_agent", "tianyancha"):
        errors.append("XRAY_COMMERCIAL 数据源名称无效")
    for name, default, minimum in (("XRAY_MAX_RUNS", "4", 1), ("XRAY_QCC_MAX_POINTS", "1500", 0),
                                    ("XRAY_COMMERCIAL_MAX_CALLS", "30", 0), ("XRAY_COMMERCIAL_CACHE_TTL", "86400", 0)):
        try:
            if int(os.getenv(name, default)) < minimum:
                raise ValueError
        except ValueError:
            errors.append(f"{name} 必须为不小于 {minimum} 的整数")
    if errors:
        raise ValueError("配置错误：" + "；".join(errors))


validate_settings()
