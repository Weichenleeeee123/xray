"""数据来源目录。分析结果里的每一条检查都用 source id 指回这里。

这是默认目录（演示数据）。某家公司有人工采集的证据包时，registry / annual_report / amac / complaints
会被证据包里的来源说明替换成 kind="collected"，见 sources/packs.py。
"""
from app.config import REF_DEPOSIT_RATE
from app.models import Source


def registry_sources(registries: dict) -> dict[str, Source]:
    """下载到本地的官方名单。中基协名单在时，"amac" 换成真实来源。"""
    out = {}
    for rid, index in registries.items():
        m = index.meta
        sid = "amac" if rid == "amac_managers" else rid
        out[sid] = Source(id=sid, name=m["title"], kind="official", as_of=m.get("as_of"), url=m.get("url"),
                          note=f"{m.get('publisher', '')}公布，共 {m.get('count', len(index)):,} 家；整份下载到本地查询")
    return out


def build_sources(license_meta: dict, registry_as_of: str, amac_as_of: str, complaints_as_of: str) -> dict[str, Source]:
    sources = [
        Source(id="nfra_bank_list", name="银行业金融机构法人名单", kind="official",
               as_of=license_meta["as_of"], url=license_meta["url"],
               note=f"{license_meta['publisher']}公布，共 {license_meta['count']} 家；只含银行业金融机构，不含证券、基金、保险、私募"),
        Source(id="registry", name="企业登记信息", kind="demo", as_of=registry_as_of,
               note="演示快照，公司为虚构；真实公司要人工到国家企业信用信息公示系统查询后存证"),
        Source(id="annual_report", name="企业年度报告", kind="demo", as_of=registry_as_of,
               note="企业自行填报、未经审计；从业人数、资产等字段企业可选择不公示"),
        Source(id="amac", name="私募基金管理人公示", kind="demo", as_of=amac_as_of,
               note="演示快照；中基协实时查询待对接"),
        Source(id="complaints", name="投诉平台", kind="demo", as_of=complaints_as_of, note="演示数据"),
        Source(id="amac_detail", name="中基协私募基金管理人公示详情页", kind="official", url="https://gs.amac.org.cn",
               note="管理规模、员工人数、资本由管理人自行填报；诚信信息、行政处罚、提示信息由协会公示"),
        Source(id="web_official", name="监管、法院、政府网站（联网搜索）", kind="official",
               note="通过比赛网关的联网搜索，只搜监管、法院、地方政府网站；只保留摘要里有公司全称的页面"),
        Source(id="web_news", name="公开报道和投诉（联网搜索）", kind="web",
               note="全网搜索\"公司名 + 投诉/维权/兑付\"；单条报道可能有误，看的是有没有、集中在什么问题"),
        Source(id="qcc_finance", name="财务数据（企查查）", kind="commercial", url="https://agent.qcc.com",
               note="企查查汇总的公司定期报告数据（上市、发债等公开披露的公司才有）；比率是平台算好的；以公告原文为准"),
        Source(id="qcc_news", name="新闻舆情（企查查）", kind="commercial", url="https://agent.qcc.com",
               note="企查查收录的新闻，负面/中立/正面是平台的模型标的，不是我们的判断；只看最近 30 条"),
        Source(id="self_description", name="公司自己的公开说法", kind="web",
               note="官网、招聘页、宣传页上公司自己写的话；只当作\"宣称\"，不当作事实"),
        Source(id="material", name="用户提供的材料", kind="user_material",
               note="宣传单、合同、聊天记录、对方回复；系统只读取上面的文字，不判断材料本身的真伪"),
        Source(id="user_reviews", name="用户评价", kind="user_review",
               note="用户自己写的评价，未经核实，系统不判断真假；只看差评是否集中，好评不算放心的理由"),
        Source(id="reg_amr", name="《关于规范金融机构资产管理业务的指导意见》", kind="regulation", as_of="2018",
               note="资产管理产品不得承诺保本保收益"),
        Source(id="reg_wm_sales", name="《商业银行理财业务监督管理办法》", kind="regulation", as_of="2018",
               note="理财产品销售文件须提示\"理财非存款、产品有风险、投资须谨慎\""),
        Source(id="reg_labor9", name="《中华人民共和国劳动合同法》第九条", kind="regulation", as_of="2012 修正",
               note="用人单位招用劳动者，不得要求劳动者提供担保或者以其他名义向劳动者收取财物"),
        Source(id="reg_pf_qualified", name="《私募投资基金监督管理暂行办法》第十二条、第十四条", kind="regulation",
               as_of="2014",
               note="私募基金只能向合格投资者募集，投资单只私募基金不低于 100 万元；个人还要金融资产不低于 300 万元或近三年年均收入不低于 50 万元；不得向不特定对象公开宣传推介"),
        Source(id="param_rate", name="一年期定期存款参考利率", kind="parameter",
               note=f"演示参数 {REF_DEPOSIT_RATE:.1%}，正式版按实际挂牌利率更新"),
    ]
    return {s.id: s for s in sources}
