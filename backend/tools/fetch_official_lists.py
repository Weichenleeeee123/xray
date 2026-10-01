"""抓取两份网页形式的官方名单，生成本地索引。

用法：
    python tools/fetch_official_lists.py futures    证监会《期货公司名录》（网页表格）
    python tools/fetch_official_lists.py payment    人民银行《已获许可机构（支付机构）》（列表页 + 每家详情页）

输出到 data/registries/<id>.csv 和 <id>.meta.json。请求之间隔 1 秒。
"""
import csv
import html
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "registries"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0"}
FUTURES_URL = "https://www.csrc.gov.cn/csrc/c101920/c1039268/content.shtml"
FUTURES_AS_OF = "2026-08"
PBC_BASE = "https://www.pbc.gov.cn"
PBC_LIST = "/zhengwugongkai/4081330/4081344/4081407/4081702/4081749/4081783/"
PBC_FIELDS = {"许可证编号": "license_no", "公司名称": "name", "住所（营业场所）": "address",
              "业务类型": "business", "业务覆盖范围": "coverage", "换证日期": "renewed", "首次许可日期": "first_licensed",
              "有效期至": "valid_until", "备注": "remark"}


def text(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).replace("\xa0", " ").strip()


def save(rid: str, rows: list[dict], fields: list[str], meta: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / f"{rid}.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    meta |= {"count": len(rows), "built_at": datetime.now().isoformat(timespec="seconds")}
    (DATA_DIR / f"{rid}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{meta['title']}：{len(rows)} 家")


def futures(client: httpx.Client) -> None:
    page = client.get(FUTURES_URL).text
    rows, region = [], ""
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, flags=re.S):
        cells = [text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)]
        if len(cells) < 2 or not cells[0].isdigit():
            continue
        if len(cells) >= 3:
            region = cells[1]   # 辖区一列跨行合并，只在每组第一行出现
        rows.append({"seq": int(cells[0]), "name": re.sub(r"\s+", "", cells[-1]), "region": region})
    if [r["seq"] for r in rows] != list(range(1, len(rows) + 1)):
        sys.exit("序号不连续，网页表格结构可能变了")
    save("csrc_futures", rows, ["seq", "name", "region"],
         {"title": "期货公司名录", "publisher": "中国证券监督管理委员会", "as_of": FUTURES_AS_OF, "url": FUTURES_URL})


def payment(client: httpx.Client) -> None:
    first = client.get(PBC_BASE + PBC_LIST + "index.html").text
    m = re.search(r"共:(\d+)条当前页:1/(\d+)", re.sub(r"\s+", "", text(first)))
    total, pages = (int(m.group(1)), int(m.group(2))) if m else (None, 1)
    prefix = re.search(r"(\w+)-\d+\.html", first)
    links: list[str] = []
    for p in range(1, pages + 1):
        body = first if p == 1 else client.get(f"{PBC_BASE}{PBC_LIST}{prefix.group(1)}-{p}.html").text
        for href in re.findall(r'href="(' + re.escape(PBC_LIST) + r'\d{10,}/index\.html)"', body):
            if href not in links:
                links.append(href)
        time.sleep(1)
    rows = []
    for i, href in enumerate(links, 1):
        lines = [l for l in (text(x) for x in re.split(r"<[^>]+>", client.get(PBC_BASE + href).text)) if l]
        # 页面先列当前信息，再列"变更前机构详细信息"；只取第一组
        start = lines.index("机构详细信息") if "机构详细信息" in lines else 0
        row = {"url": PBC_BASE + href}
        for j in range(start, len(lines) - 1):
            if lines[j].startswith("变更前"):
                break
            if lines[j] in PBC_FIELDS and PBC_FIELDS[lines[j]] not in row:
                row[PBC_FIELDS[lines[j]]] = lines[j + 1]
        if row.get("name"):
            rows.append(row)
        if i % 30 == 0:
            print(f"  {i}/{len(links)}", flush=True)
        time.sleep(1)
    if total and len(rows) != total:
        print(f"注意：列表页说 {total} 条，解析到 {len(rows)} 条")
    save("pbc_payment", rows, list(PBC_FIELDS.values()) + ["url"],
         {"title": "已获许可机构（支付机构）", "publisher": "中国人民银行", "as_of": datetime.now().date().isoformat(),
          "url": PBC_BASE + PBC_LIST + "index.html", "note": "as_of 为抓取日期；列表含已续展、变更的现存机构"})


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("futures", "payment"):
        sys.exit(__doc__)
    with httpx.Client(headers=UA, timeout=30, follow_redirects=True) as c:
        {"futures": futures, "payment": payment}[sys.argv[1]](c)
