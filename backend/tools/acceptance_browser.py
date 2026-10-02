"""Real-browser acceptance; explicitly opt in to paid gateway calls with --live.

Uses only a new isolated temp case/cache directory, never existing user cases.
Outputs contain public demo records, screenshots and model replies, but no keys.
Run from backend: python tools/acceptance_browser.py --live
Requires requirements-browser.txt and Microsoft Edge (or Playwright Chromium).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parent


def check_known_answer(kind: str, reply: dict, expected_refs: set[str]) -> None:
    text = reply["text"].replace(",", "").replace("，", "").replace(" ", "")
    assert set(reply["citations"]) & expected_refs, "Answer must cite the relevant source record"
    if kind == "penalty":
        assert "2024" in text and re.search(r"(?<![\d.])36万元(?:的)?罚款|罚款(?:金额)?(?:为|：|:)?36万元", text)
    else:
        assert "38798611元" not in text
        assert re.search(r"营业收入[^。；\n]*(?<![\d.])38798611[（(]?(?:人民币)?千元|"
                         r"营业收入[（(]?(?:人民币)?千元[）)]?[^。；\n]*(?<![\d.])38798611(?![\d.])", text)


def serve(port: int) -> None:
    # Test-only network guard: replay must not depend on an external HTTP request.
    if os.getenv("XRAY_ACCEPTANCE_BLOCK_NETWORK") == "1":
        import httpx

        def blocked(*args, **kwargs):
            print("ACCEPTANCE_EXTERNAL_HTTP_ATTEMPT", flush=True)
            raise RuntimeError("External network forbidden during replay acceptance")

        httpx.Client.send = blocked
        httpx.AsyncClient.send = blocked
    import uvicorn
    sys.path.insert(0, str(BASE))
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="warning")


def run(live: bool, commercial: bool = False, seed_cache: Path | None = None) -> None:
    import pdfplumber
    from playwright.sync_api import sync_playwright
    logging.getLogger("pdfminer").setLevel(logging.ERROR)

    parent = ROOT / ".tmp"
    parent.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="browser-acceptance-", dir=parent))
    if seed_cache is not None:
        # Copy previous acceptance recordings; never mutate the source cache.
        shutil.copytree(seed_cache, out / "cache")
    cases = out / "cases"
    cases.mkdir()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    report: dict = {"output": str(out), "live": live, "commercial": commercial, "checks": [], "timings": {}, "warnings": []}
    proc, log = None, None

    def mark(name: str, **details):
        report["checks"].append({"name": name, **details})
        print(json.dumps({"check": name, **details}, ensure_ascii=False), flush=True)

    def stop():
        nonlocal proc, log
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            proc = None
        if log:
            log.close()
            log = None

    def start(mode: str, blocked: bool = False):
        nonlocal proc, log
        env = dict(os.environ, XRAY_CASES_DIR=str(cases), XRAY_CACHE_DIR=str(out / "cache"), XRAY_REVIEWS_DIR=str(out / "reviews"),
                   XRAY_LLM_MODE=mode, XRAY_COMMERCIAL="qcc_agent" if commercial and not blocked else "", PYTHONIOENCODING="utf-8",
                   XRAY_ACCEPTANCE_BLOCK_NETWORK="1" if blocked else "0",
                   XRAY_AMAC_DETAIL="0" if blocked or not live else "1")
        log = (out / f"server-{mode}.log").open("w", encoding="utf-8")
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve", str(port)],
                                cwd=BASE, env=env, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"Server exited; inspect {out / f'server-{mode}.log'}")
            try:
                with urlopen(base + "/api/health", timeout=1) as response:
                    health = json.load(response)
                assert health["llm"]["mode"] == mode
                if live:
                    assert health["llm"]["configured"], "Live test requires configured gateway"
                if commercial and not blocked:
                    assert health["commercial"]["configured"], "Commercial test requires configured QCC keys"
                return health
            except OSError:
                time.sleep(0.1)
        raise TimeoutError("Local acceptance server did not start")

    question = "请说明浙江证监局2024年对这家公司作出的处罚结果，引用原始记录，不推测后果。"
    errors: list[str] = []
    try:
        health = start("live" if live else "off")
        mark("health", model=health["llm"]["model"], evidence_packs=health["evidence_packs"])
        with sync_playwright() as pw:
            edge = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
            browser = pw.chromium.launch(headless=True, **({"executable_path": str(edge)} if edge.exists() else {}))
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            page.on("pageerror", lambda err: errors.append(str(err)))
            page.set_default_timeout(15000)

            def state():
                return page.evaluate("S.case")

            def create(which: str):
                page.goto(base + "/xray/#/new")
                # Observe the actual consumer: it cancels/releases the stream after
                # the terminal event, so CDP may no longer retain response.body().
                page.evaluate("""() => {
                  window.acceptanceProgress = [];
                  const read = window.acceptanceOriginalRead ||= ResearchProgress.readCaseStream;
                  ResearchProgress.readCaseStream = async (url, body, options) => {
                    const result = await read(url, body, { ...options, onEvent: event => {
                      acceptanceProgress.push(event); options.onEvent(event);
                    }});
                    acceptanceProgress.push({type:'case', case:result});
                    return result;
                  };
                }""")
                page.locator(f'[data-act="demo-fill"][data-id="{which}"]').click()
                # Wait for the actual intake request before submitting, as an operator would.
                page.wait_for_function("!document.querySelector('#intake').classList.contains('busy')")
                t = time.monotonic()
                with page.expect_response(lambda r: r.url.endswith("/api/cases/stream") and r.request.method == "POST", timeout=180000) as response:
                    page.locator("#fSubmit").click()
                assert response.value.ok, response.value.status
                if live:
                    page.locator('.research-wait').screenshot(path=str(out / f'{which}-waiting.png'))
                page.wait_for_function("S.case && location.hash.includes(S.case.id)", timeout=180000)
                events = page.evaluate('acceptanceProgress')
                assert events[0]['type'] == 'begin' and events[-1]['type'] == 'case'
                planned = [s['id'] for s in events[0]['steps']]
                sequence = [(e['id'], e['phase']) for e in events if e['type'] == 'step']
                assert sequence == [(s, p) for s in planned for p in ('start', 'done')], sequence
                result = events[-1]['case']
                if commercial:
                    registry = [e for e in events if e.get('id') == 'registry' and e.get('phase') == 'done']
                    assert len(registry) == 1 and registry[0].get('coverage') == 'found', registry
                    with urlopen(base + '/api/health', timeout=5) as health_response:
                        commercial_status = json.load(health_response)['commercial']
                    mark(f'qcc_{which}', coverage='found', points=commercial_status['points'],
                         max_points=commercial_status['max_points'])
                page.wait_for_function("id => S.case?.id === id && location.hash.includes(id)", arg=result['id'], timeout=180000)
                assert state()["id"] == result["id"]
                report["timings"][f"create_{which}"] = round(time.monotonic() - t, 2)
                mark(f"create_{which}", versions=result["current"], real=which in ("A", "B"))
                return result

            def ask(text: str):
                t = time.monotonic()
                with page.expect_response(lambda r: r.url.endswith("/chat") and r.request.method == "POST", timeout=240000) as response:
                    page.locator("#asForm textarea").fill(text)
                    page.locator('#asForm button[type="submit"]').click()
                assert response.value.ok, response.value.status
                page.wait_for_function("!S.busy")
                reply = response.value.json()
                mark("chat", mode=reply["mode"], version=reply["version"],
                     citations=reply["citations"], dropped=reply["dropped"], rewrites=reply["rewrites"],
                     seconds=round(time.monotonic() - t, 2))
                return reply

            def print_page(label: str):
                if not page.locator('[data-act="aud"][data-aud="family"]').is_visible():
                    page.locator('[data-act="optext"]').click()
                page.wait_for_function("Boolean(document.querySelector('#onepager')) && Boolean(currentOp(ver()))")
                path = out / f"{label}.pdf"
                page.pdf(path=str(path), format="A4", print_background=True, prefer_css_page_size=True)
                with pdfplumber.open(path) as pdf:
                    count = len(pdf.pages)
                    # Chromium stores superscript references after body text in
                    # the PDF stream. Verify both, without assuming visual order.
                    text = "\n".join(p.extract_text(use_text_flow=True) or "" for p in pdf.pages)
                assert state()["case"]["company_name"] in text
                flattened = re.sub(r"\s+", "", text)
                paragraphs = page.locator("#onepager .op-col li, #onepager .op-next li, #onepager .op-foot").evaluate_all(
                    "els => els.map(el => {const copy=el.cloneNode(true); copy.querySelectorAll('.rf').forEach(r=>r.remove()); return copy.textContent;})")
                paragraphs += page.locator("#onepager .rf").all_inner_texts()
                for paragraph in paragraphs:
                    assert re.sub(r"\s+", "", paragraph) in flattened, "Printed report lost a paragraph or its references"
                mark("print", label=label, pages=count)
                if count != 1:
                    report["warnings"].append(f"{label}: expected one A4 page, got {count}")

            case_a = create("A")
            # Preserve the server's exact JSON number types. A JS round trip
            # changes raw numeric 100.0 to 100 and no longer has the same cache key.
            with urlopen(base + '/api/cases/' + case_a['id'], timeout=5) as snapshot_response:
                before = json.load(snapshot_response)
            (out / "replay-before-chat.json").write_text(json.dumps(before, ensure_ascii=False), encoding="utf-8")
            assert not page.locator("#topBadges").get_by_text("公司为虚构").count()
            record = next(r for r in case_a["raw"] if r["source_id"] == "jujing_csrc_2024")
            page.locator('.tabs [data-act="tab"][data-tab="raw"]').click()
            page.locator(f'.raw-row[data-ref="{record["id"]}"]').click()
            assert "2024-09-13" in page.locator("#rawDlg").inner_text()
            assert page.locator("#rawDlg a").get_attribute("href").startswith("https://www.csrc.gov.cn/")
            page.locator('#rawDlg [data-act="close-dlg"]').click()
            reply_live = ask(question)
            assert reply_live["version"] == 1
            if live:
                assert reply_live["mode"] == "model", "Live answer must actually come from the model"
                assert not reply_live["not_found"] and reply_live["citations"], "Known penalty must have grounded citations"
                penalty_refs = {r["id"] for r in case_a["raw"] if r["kind"] in ("official", "collected")
                                and "2024" in json.dumps(r["content"], ensure_ascii=False)
                                and "36万元罚款" in json.dumps(r["content"], ensure_ascii=False)}
                check_known_answer("penalty", reply_live, penalty_refs)
            after_chat = page.request.get(f'{base}/api/cases/{case_a["id"]}').json()
            assert after_chat["versions"] == before["versions"] and after_chat["raw"] == before["raw"]
            mark("chat_did_not_change_evidence_or_report")
            for i, expected in ((0, 2), (1, 3)):
                page.locator('[data-act="supplement"]').first.click()
                page.locator(f'#supDlg [data-act="sup-fill"][data-i="{i}"]').click()
                with page.expect_response(lambda r: r.url.endswith("/supplements/stream") and r.request.method == "POST", timeout=180000) as response:
                    page.locator("#supGo").click()
                assert response.value.ok, response.value.status
                page.wait_for_function(f"S.case.current === {expected}", timeout=180000)
                v = state()["versions"][-1]
                assert v["changes"]
                mark("supplement", version=expected, changes={k: sum(c["kind"] == k for c in v["changes"]) for k in {c["kind"] for c in v["changes"]}})
            # Every historical citation should switch the view back before opening its record.
            citation = page.locator('.msg.ai [data-act="goto"][data-version="1"]').first
            if citation.count():
                citation.click()
                assert page.evaluate("ver().no") == 1
                if page.locator("#rawDlg").evaluate("el => el.open"):
                    page.locator('#rawDlg [data-act="close-dlg"]').click()
                mark("historical_citation_navigation")
            else:
                if live:
                    raise AssertionError("Live answer supplied no clickable historical citation")
            page.locator('.vers [data-act="ver"][data-no="1"]').click()
            page.wait_for_function("ver().no === 1")
            old_reply = ask("它有没有资格收这笔钱？")
            assert old_reply["version"] == 1 and state()["current"] == 3
            if live:
                assert old_reply["mode"] == "model" and not old_reply["not_found"] and old_reply["citations"]
            mark("old_version_question_without_selection")
            page.locator('.vers [data-act="ver"][data-no="3"]').click()
            page.wait_for_function("ver().no === 3")
            (out / "A-v3-snapshot.json").write_text(json.dumps(state(), ensure_ascii=False), encoding="utf-8")
            page.screenshot(path=str(out / "A-v3.png"), full_page=True)
            print_page("A-v3-family")
            page.locator('[data-act="aud"][data-aud="teller"]').click()
            print_page("A-v3-teller")
            case_b = create("B")
            page.locator('[data-act="aud"][data-aud="family"]').click()
            bank_reply = ask("2025年年报披露的营业收入是多少？请保持原表的人民币千元单位，并引用原始记录。")
            assert bank_reply["version"] == 1
            if live:
                assert bank_reply["mode"] == "model" and not bank_reply["not_found"] and bank_reply["citations"]
                bank_refs = {r["id"] for r in case_b["raw"] if r["source_id"] == "hzbank_annual_2025"}
                check_known_answer("revenue", bank_reply, bank_refs)
            page.screenshot(path=str(out / "B-v1.png"), full_page=True)
            print_page("B-v1-family")
            page.set_viewport_size({"width": 375, "height": 812})
            page.screenshot(path=str(out / "B-mobile.png"), full_page=True)
            overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth")
            mark("mobile_width", horizontal_overflow=overflow)
            if overflow:
                mark('overflow_elements', elements=page.evaluate("""[...document.querySelectorAll('body *')]
                  .map(el => ({tag:el.tagName, id:el.id, cls:el.className, right:el.getBoundingClientRect().right}))
                  .filter(el => el.right > innerWidth + 1).slice(0, 12)"""))
                report["warnings"].append("Mobile layout has horizontal overflow")
            if page.locator("#assist").evaluate("el => el.classList.contains('open')"):
                page.locator('[data-act="close-assist"]').click()
            page.locator('[data-act="open-assist"]').click()
            assert page.locator("#assist").evaluate("el => el.classList.contains('open')")
            fallback = page.goto(base + "/demo/")
            assert fallback and fallback.ok
            assert "透视" in page.title() and "公司" in page.locator("body").inner_text()
            mark("static_fallback_loaded")
            context.close()
            stop()
            if live:
                # Restore only this test's own pre-question snapshot, not user data.
                target = cases / f'{before["id"]}.json'
                assert target.resolve().parent == cases.resolve() and before["id"].isalnum()
                target.write_text(json.dumps(before, ensure_ascii=False), encoding="utf-8")
                start("replay", blocked=True)
                offline = browser.new_context(viewport={"width": 1440, "height": 1000})
                external = []

                def restrict(route):
                    if route.request.url.startswith(base + "/"):
                        route.continue_()
                    else:
                        external.append(route.request.url.split("?", 1)[0])
                        route.abort()

                offline.route("**/*", restrict)
                page = offline.new_page()
                page.on("pageerror", lambda err: errors.append(str(err)))
                page.goto(f'{base}/xray/#/case/{before["id"]}/v/1')
                page.locator("#report").wait_for()
                assert "离线回放" in page.locator("#topBadges").inner_text()
                replay = ask(question)
                assert replay["mode"] == "replay" and replay["recorded_at"] and not replay["not_found"]
                assert replay["text"] == reply_live["text"] and replay["citations"] == reply_live["citations"]
                page.screenshot(path=str(out / "A-offline-replay.png"), full_page=True)
                mark("offline_replay_same_snapshot", external_browser_requests=len(external))
                miss = ask("请给出案卷里没有记录的明天实时营业额")
                assert miss["mode"] in ("template", "guard") and miss["not_found"]
                mark("offline_cache_miss_labeled", mode=miss["mode"])
                offline.close()
                stop()
                assert "ACCEPTANCE_EXTERNAL_HTTP_ATTEMPT" not in (out / "server-replay.log").read_text(encoding="utf-8")
                mark("offline_backend_no_external_http")
            browser.close()
            assert not errors, errors
            mark("no_browser_javascript_errors")
        assert not report["warnings"], "; ".join(report["warnings"])
        report["completed"] = True
    except Exception as exc:
        report["completed"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        stop()
        (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("ACCEPTANCE_RESULT=" + str(out / "result.json"), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Call the configured gateway using public demo cases")
    parser.add_argument("--commercial", action="store_true", help="Explicitly enable paid QCC queries with the configured point cap")
    parser.add_argument("--seed-cache", type=Path, help="Copy a previous acceptance cache to avoid repeat paid company queries")
    parser.add_argument("--serve", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve:
        serve(args.serve)
    else:
        run(args.live, args.commercial, args.seed_cache)
