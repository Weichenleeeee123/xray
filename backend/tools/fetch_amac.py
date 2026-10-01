"""把中基协"私募基金管理人综合查询"的全量名单拉到本地（公开接口，无验证码），生成索引。

用法：
    python tools/fetch_amac.py

输出：
    data/registries/amac_managers.csv        机构名称、登记编号、成立/登记日期、在管基金数、机构类型、
                                             是否有"特别提示"和"诚信信息"、注册地、详情页链接
    data/registries/amac_managers.meta.json  来源、抓取时间、条数

每页 100 条，请求之间隔 1 秒，不给对方服务器添负担。
"""
import csv
import json
import random
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "registries"
API = "https://gs.amac.org.cn/amac-infodisc/api/pof/manager"
DETAIL = "https://gs.amac.org.cn/amac-infodisc/res/pof/manager/"
PAGE_SIZE = 100
CST = timezone(timedelta(hours=8))
FIELDS = ["name", "register_no", "established", "registered", "fund_count", "invest_type", "org_form",
          "member_type", "special_tips", "credit_tips", "province", "city", "detail_url"]


def day(ms: int | None) -> str:
    return datetime.fromtimestamp(ms / 1000, CST).date().isoformat() if ms else ""


def row(m: dict) -> dict:
    return {"name": m["managerName"], "register_no": m.get("registerNo") or "",
            "established": day(m.get("establishDate")),
            "registered": day(m.get("registerDate")), "fund_count": m.get("fundCount") or 0,
            "invest_type": m.get("primaryInvestType") or "", "org_form": m.get("orgForm") or "",
            "member_type": m.get("memberType") or "", "special_tips": int(bool(m.get("hasSpecialTips"))),
            "credit_tips": int(bool(m.get("hasCreditTips"))), "province": m.get("registerProvince") or "",
            "city": m.get("registerCity") or "", "detail_url": DETAIL + (m.get("url") or "")}


def fetch_page(client: httpx.Client, page: int) -> dict:
    for attempt in range(3):
        try:
            r = client.post(API, params={"rand": random.random(), "page": page, "size": PAGE_SIZE}, json={})
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            time.sleep(3 * (attempt + 1))
    raise SystemExit(f"第 {page} 页连续失败，停止")


def main() -> None:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0",
               "Referer": "https://gs.amac.org.cn/amac-infodisc/res/pof/manager/index.html"}
    rows: list[dict] = []
    with httpx.Client(headers=headers, timeout=30) as client:
        first = fetch_page(client, 0)
        total, pages = first["totalElements"], first["totalPages"]
        rows += [row(m) for m in first["content"]]
        for page in range(1, pages):
            time.sleep(1)
            rows += [row(m) for m in fetch_page(client, page)["content"]]
            if page % 20 == 0:
                print(f"  {page}/{pages} 页，{len(rows)} 条", flush=True)

    names = {r["name"] for r in rows}
    if len(rows) != total or len(names) < total * 0.99:
        sys.exit(f"条数对不上：接口说 {total}，拿到 {len(rows)}（去重 {len(names)}），可能翻页期间数据有变动，重跑一次")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / "amac_managers.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    now = datetime.now(CST).isoformat(timespec="seconds")
    meta = {"title": "私募基金管理人公示", "publisher": "中国证券投资基金业协会", "as_of": now[:10],
            "url": "https://gs.amac.org.cn/amac-infodisc/res/pof/manager/index.html", "count": len(rows),
            "built_at": now, "note": "全量名单按登记日期排序分页抓取；special_tips=有特别提示信息，credit_tips=有诚信信息"}
    (DATA_DIR / "amac_managers.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"共 {len(rows)} 家；有特别提示 {sum(r['special_tips'] for r in rows)} 家，有诚信信息 {sum(r['credit_tips'] for r in rows)} 家")


if __name__ == "__main__":
    main()
