"""Offline browser check of need-led summaries; only isolated fictional cases.

Run from backend: python tools/acceptance_company_summary.py
Uses installed Playwright and Edge/Chromium, never a paid API or existing cases.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))


def run():
    from playwright.sync_api import sync_playwright

    out = Path(tempfile.mkdtemp(prefix="qier-company-summary-"))
    cases = out / "cases"
    env = dict(os.environ, XRAY_CASES_DIR=str(cases), XRAY_CACHE_DIR=str(out / "cache"),
               XRAY_REVIEWS_DIR=str(out / "reviews"), XRAY_RUNS_DIR=str(out / "runs"),
               XRAY_PRIVATE_DIR=str(out / "private"), XRAY_CASE_MEMORY_ENABLED="0",
               XRAY_DEMO_PREBUILT_DIR=str(out / "prebuilt"), XRAY_LLM_MODE="off",
               XRAY_COMMERCIAL="", XRAY_AMAC_DETAIL="0", XRAY_CNINFO="0",
               XRAY_WEB_DISCOVERY="0", XRAY_WEB_DISCOVERY_LLM="0",
               XRAY_QUOTA_GUEST="0", XRAY_QUOTA_ACCOUNT="0", XRAY_QUOTA_IP="0",
               XRAY_RESEND_KEY="", XRAY_ACCEPTANCE_BLOCK_NETWORK="1", PYTHONIOENCODING="utf-8")
    os.environ.update(env)
    from app.models import Case, RawRecord, Source, Status
    from tests.helpers import DEMO_COMPANY
    from tests.test_company_summary import report, record

    variants = {
        "general": report(penalties="bad"),
        "job": report("job", "我想来这里入职", ("credit", [record("labor", "无", label="劳动仲裁")]), penalties="bad"),
        "savings": report("savings", "想在这里存钱", ("risk", [record("bank_list", "查到名单记录", label="金融机构名单")]), penalties="bad"),
        "unknown": report("job", "想了解这家公司的用工情况"),
        "critical": report("job", "想了解是否适合入职"),
    }
    variants["critical"].signals[0].items[0].status = Status.bad
    variants["critical"].signals[0].items[0].value = "吊销"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    checks, errors = [], []
    with (out / "server.log").open("w", encoding="utf-8") as log:
        proc = subprocess.Popen([sys.executable, str(BASE / "tools/acceptance_browser.py"), "--serve", str(port)],
                                cwd=BASE, env=env, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 25
            while True:
                try:
                    with urlopen(base + "/api/health", timeout=1) as response:
                        assert json.load(response)["llm"]["mode"] == "off"
                    break
                except OSError:
                    if proc.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Local isolated server did not start")
                    time.sleep(0.1)
            with sync_playwright() as pw:
                edge = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
                browser = pw.chromium.launch(headless=True, **({"executable_path": str(edge)} if edge.exists() else {}))
                context = browser.new_context(viewport={"width": 1440, "height": 1100})
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.set_default_timeout(10000)
                for name, version in variants.items():
                    response = context.request.post(base + "/api/cases", data={"company_name": DEMO_COMPANY, "need": version.need})
                    assert response.ok, response.status
                    # The public DTO deliberately omits owner_id. Preserve the
                    # real guest ownership from our own newly created temp file.
                    case_id = response.json()["id"]
                    case = Case.model_validate_json((cases / f"{case_id}.json").read_text(encoding="utf-8"))
                    # Seed only this newly created temporary case. Every replaced
                    # source is explicitly labelled fictional and points to R900.
                    for signal in version.signals:
                        signal.title = {"credit": "信用", "risk": "风险", "finance": "财务", "reputation": "口碑"}[signal.key]
                        for item in signal.items:
                            item.source, item.ref = "preview", "R900"
                            if item.label.startswith("核查"):
                                item.label = {"status": "登记状态", "penalties": "行政处罚", "abnormal": "经营异常名录",
                                              "serious_illegal": "严重违法失信名单", "dishonest": "失信被执行人"}[item.key]
                            if item.value.startswith("记录"):
                                item.value = "1 条" if item.status == "bad" else "未查到记录"
                    source = Source(id="preview", name="虚构界面验收记录", kind="demo", as_of="2026-10-04")
                    version.sources, version.raw_ids = {"preview": source}, ["R900"]
                    version.charts, version.questions, version.judgments, version.notes = [], [], [], ["仅用于界面验收的虚构记录。"]
                    version.company_keywords, version.assertions, version.missing = [], [], []
                    version.company, version.onepager, version.overview = None, None, None
                    case.versions, case.current, case.sources = [version], 1, version.sources
                    case.case.need, case.case.scenario = version.need, version.scenario
                    case.raw = [RawRecord(id="R900", source_id="preview", kind="demo", title="虚构界面验收数据",
                                          retrieved_at="2026-10-04T00:00:00Z", as_of="2026-10-04",
                                          content={s.key: [i.model_dump() for i in s.items] for s in version.signals})]
                    (cases / f"{case.id}.json").write_text(case.model_dump_json(), encoding="utf-8")
                    page.goto(base + f"/xray/#/case/{case.id}")
                    page.locator("[data-summary-tone]").wait_for()
                    headline = page.locator("#verdict-title").inner_text()
                    assert "信任度" not in headline
                    assert page.locator(".overview-basis button").count() > 0
                    assert page.locator(".decision-next").inner_text().find("后续可选") >= 0
                    if name == "job":
                        assert "劳动仲裁" in headline and "行政处罚" in headline
                    if name == "critical":
                        assert "吊销" in headline and page.locator("[data-summary-tone]").get_attribute("data-summary-tone") == "critical"
                    for width in (1440, 1920):
                        page.set_viewport_size({"width": width, "height": 1100})
                        assert page.locator("#verdict-title").evaluate("el => el.scrollWidth <= el.clientWidth + 1")
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                        page.locator("#research-overview").screenshot(path=str(out / f"{name}-{width}.png"))
                    page.locator(".overview-basis button").first.click()
                    page.locator("#signalDlg").wait_for(state="visible")
                    page.locator('#signalDlg [data-act="raw"]').first.click()
                    assert page.locator("#rawDlg").is_visible()
                    assert "虚构界面验收" in page.locator("#rawDlg").inner_text()
                    checks.append({"case": name, "headline": headline, "evidence_navigation": True})
                    page.evaluate("document.querySelectorAll('dialog[open]').forEach(d=>d.close())")
                assert not errors, errors
                browser.close()
            print(json.dumps({"passed": checks, "console_errors": errors, "output": str(out)}, ensure_ascii=False), flush=True)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            print("BROWSER_OUTPUT=" + str(out), flush=True)
    assert "ACCEPTANCE_EXTERNAL_HTTP_ATTEMPT" not in (out / "server.log").read_text(encoding="utf-8")


if __name__ == "__main__":
    run()
