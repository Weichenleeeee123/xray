"""开查之前把公司名定成全称：精确对上直接用；简称给候选让用户选，不替用户挑；断网用本地名单兜底。
企查查用本地假响应，不连网、不扣积分。"""
import json
from dataclasses import replace

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.sources.qcc_agent import QccAgentClient
from app.sources.resolve import resolve
from tests.helpers import svc

# 假响应，照平台"多候选"的结构写；公司和代码都是虚构的
MULTI = {"匹配结果": "多候选", "检索关键字": "测试财富", "摘要": "命中多个相关主体，无法自动锁定。",
         "企业信息": [{"企业名称": "杭州测试财富管理有限公司", "统一社会信用代码": "91330100TEST00002X",
                      "成立日期": "2015-04-01", "法定代表人名称": ["甲某"], "状态": "存续"},
                     {"企业名称": "杭州测试资产管理有限公司", "统一社会信用代码": "91330100TEST00003X",
                      "成立日期": "2016-01-01", "法定代表人名称": ["甲某"], "状态": "存续"}]}
UNIQUE = {"匹配结果": "唯一精确匹配", "检索关键字": "杭州测试科技有限公司",
          "企业信息": {"企业名称": "杭州测试科技有限公司", "统一社会信用代码": "91330100TEST00001X"}}


def qcc(tmp_path, answer=None, offline=False, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content)["params"]["arguments"]["searchKey"])
        if offline:
            raise httpx.ConnectError("断网")
        msg = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": json.dumps(answer, ensure_ascii=False)}]}}
        return httpx.Response(200, json=msg)
    return replace(svc, commercial=QccAgentClient("Bearer K", cache_dir=tmp_path, transport=httpx.MockTransport(handler)))


def test_full_name_in_local_lists_needs_no_lookup(tmp_path):
    seen = []
    r = resolve("杭州银行股份有限公司", qcc(tmp_path, UNIQUE, seen=seen))
    assert r.exact and r.name == "杭州银行股份有限公司" and r.source == "local" and not seen


def test_short_name_returns_candidates_without_personal_names(tmp_path):
    r = resolve("测试财富", qcc(tmp_path, MULTI))
    assert not r.exact and r.name is None and r.source == "qcc"
    assert [c.name for c in r.candidates] == ["杭州测试财富管理有限公司", "杭州测试资产管理有限公司"]
    assert r.candidates[0].code == "91330100TEST00002X" and r.candidates[0].status == "存续"
    assert "甲某" not in json.dumps([c.__dict__ for c in r.candidates], ensure_ascii=False)


def test_unique_exact_match_is_accepted(tmp_path):
    r = resolve("杭州测试科技有限公司", qcc(tmp_path, UNIQUE))
    assert r.exact and r.name == "杭州测试科技有限公司"


def test_unique_but_different_name_is_offered_not_assumed(tmp_path):
    r = resolve("测试科技", qcc(tmp_path, dict(UNIQUE, 检索关键字="测试科技")))
    assert not r.exact and [c.name for c in r.candidates] == ["杭州测试科技有限公司"]


def test_offline_falls_back_to_local_lists(tmp_path):
    r = resolve("巨鲸财富", qcc(tmp_path, offline=True))
    assert not r.exact and r.source == "local" and "杭州巨鲸财富管理有限公司" in [c.name for c in r.candidates]
    assert "没成功" in r.note


def test_unknown_name_asks_for_the_full_name(tmp_path):
    r = resolve("完全不存在的某某某某公司名", qcc(tmp_path, {"匹配结果": "无结果", "企业信息": []}))
    assert not r.exact and not r.candidates and "全称" in r.note


def test_resolve_api():
    body = TestClient(app).get("/api/companies/resolve", params={"q": "杭州银行股份有限公司"}).json()
    assert body["exact"] and body["name"] == "杭州银行股份有限公司"
