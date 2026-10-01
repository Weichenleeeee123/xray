# X-Ray 后端：前期数据获取与分析

## 运行

```
cd backend
.venv\Scripts\python -m uvicorn app.main:app --port 8000 --reload
```

- 接口文档：http://localhost:8000/docs
- 测试：`.venv\Scripts\python -m pytest`
- 新机器上先装依赖：`python -m venv .venv`，再 `.venv\Scripts\pip install -r requirements.txt`

## 数据来源

| 数据 | 真实 / 演示 | 文件 |
|---|---|---|
| 持牌机构名单 | **真实**：金融监管总局《银行业金融机构法人名单》，截至 2025-06-30，共 4070 家 | `data/licensed_institutions.csv` |
| 企业登记、年报、处罚、股权出质 | 演示，公司全部虚构 | `data/fixtures/companies.json` |
| 私募基金管理人登记 | 演示（中基协实时接口在本地测试返回 500） | `data/fixtures/amac.json` |
| 投诉 | 演示 | `data/fixtures/complaints.json` |
| 宣传单 | 用户提交的文字；图片要接模型或 OCR，暂未接 | `data/fixtures/flyers/` |

持牌名单只覆盖银行业金融机构，不含证券、基金、保险、私募，所以"没查到"不等于"没有牌照"。

更新名单（金融监管总局发布新版 PDF 后）：

```
.venv\Scripts\python tools\build_license_index.py data\raw\<名单>.pdf <截至日期> <原文链接>
```

## 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` | 服务状态、名单条数和日期 |
| GET | `/api/sources` | 全部数据来源（真实 / 演示 / 法规 / 参数） |
| GET | `/api/licenses/check?name=` | 查任意机构是否持牌；输入简称会返回候选全称 |
| GET | `/api/companies/profile?name=` | 企业记录 + 持牌 + 私募登记 |
| GET | `/api/demo` | 演示案卷的输入（含宣传单文字） |
| POST | `/api/cases` | 建案卷并完成前期分析：宣称核验 + 四个信号 |
| GET | `/api/cases/{id}` | 取回案卷（内存存储，重启清空） |

## 约定

- 结论全部来自 `app/analysis/verify.py` 里的确定性规则，同样的输入永远得到同样的结论。以后接大模型，只让它做"读材料、找说法、给原文"（实现 `ClaimExtractor` 接口），不让它下结论。
- 每条检查都带 `source`，指回 `/api/sources`。数据源没覆盖的，写"没查"（`status: none`），不把没数据说成没问题。
- 加一家演示公司：在 `companies.json` 加一条，需要的话在 `amac.json` 的 `covered` 和 `complaints.json` 里补上。
