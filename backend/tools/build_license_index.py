"""从金融监管总局公布的《银行业金融机构法人名单》PDF 生成本地索引。

用法：
    python tools/build_license_index.py <名单.pdf> <截至日期 YYYY-MM-DD> <原文链接>

输出：
    data/licensed_institutions.csv        序号、中文全称、英文全称、机构编码、机构类型、监管责任单位
    data/licensed_institutions.meta.json  来源链接、截至日期、条数、生成时间
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import pdfplumber

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIELDS = ["seq", "name", "name_en", "code", "type", "regulator"]


def zh(cell: str | None) -> str:
    return "".join((cell or "").split())


def en(cell: str | None) -> str:
    return " ".join((cell or "").split())


def extract_rows(pdf_path: Path) -> list[dict]:
    rows: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for cells in page.extract_table() or []:
                if not cells or len(cells) < 6 or zh(cells[0]) == "序号":
                    continue
                seq = zh(cells[0])
                if seq.isdigit():
                    rows.append({
                        "seq": int(seq), "name": zh(cells[1]), "name_en": en(cells[2]),
                        "code": zh(cells[3]), "type": zh(cells[4]), "regulator": zh(cells[5]),
                    })
                elif rows and any(cells[1:]):
                    # 跨页被截断的行：把续行拼回上一行
                    last = rows[-1]
                    last["name"] += zh(cells[1])
                    last["name_en"] = en(f"{last['name_en']} {cells[2] or ''}")
                    last["code"] += zh(cells[3])
                    last["type"] += zh(cells[4])
                    last["regulator"] += zh(cells[5])
    return rows


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    pdf_path, as_of, url = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    rows = extract_rows(pdf_path)

    seqs = [r["seq"] for r in rows]
    if seqs != list(range(1, len(rows) + 1)):
        gaps = sorted(set(range(1, max(seqs) + 1)) - set(seqs))[:10]
        sys.exit(f"序号不连续，解析可能有误：缺 {gaps}")

    DATA_DIR.mkdir(exist_ok=True)
    with open(DATA_DIR / "licensed_institutions.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    meta = {
        "title": "银行业金融机构法人名单",
        "publisher": "国家金融监督管理总局",
        "as_of": as_of,
        "url": url,
        "count": len(rows),
        "source_file": pdf_path.name,
        "built_at": datetime.now().isoformat(timespec="seconds"),
    }
    (DATA_DIR / "licensed_institutions.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    types: dict[str, int] = {}
    for r in rows:
        types[r["type"]] = types.get(r["type"], 0) + 1
    print(f"共 {len(rows)} 家，截至 {as_of}")
    for t, n in sorted(types.items(), key=lambda kv: -kv[1]):
        print(f"  {t}: {n}")


if __name__ == "__main__":
    main()
