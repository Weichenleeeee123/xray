"""数据来源目录。分析结果里的每一条检查都用 source id 指回这里。"""
from app.config import REF_DEPOSIT_RATE
from app.models import Source


def build_sources(license_meta: dict, registry_as_of: str, amac_as_of: str, complaints_as_of: str) -> dict[str, Source]:
    sources = [
        Source(id="nfra_bank_list", name="银行业金融机构法人名单", kind="official",
               as_of=license_meta["as_of"], url=license_meta["url"],
               note=f"{license_meta['publisher']}公布，共 {license_meta['count']} 家；只含银行业金融机构，不含证券、基金、保险、私募"),
        Source(id="registry", name="企业登记信息", kind="demo", as_of=registry_as_of,
               note="演示快照，公司为虚构；正式版接入企业信用信息公示系统或企查查等授权接口"),
        Source(id="annual_report", name="企业年度报告", kind="demo", as_of=registry_as_of,
               note="企业自行填报、未经审计；从业人数、资产等字段企业可选择不公示"),
        Source(id="amac", name="私募基金管理人公示", kind="demo", as_of=amac_as_of,
               note="演示快照；中基协实时查询待对接"),
        Source(id="complaints", name="投诉平台", kind="demo", as_of=complaints_as_of, note="演示数据"),
        Source(id="flyer", name="宣传材料（用户上传）", kind="user_material",
               note="系统只读取材料上的文字，不判断材料本身的真伪"),
        Source(id="reg_amr", name="《关于规范金融机构资产管理业务的指导意见》", kind="regulation", as_of="2018",
               note="资产管理产品不得承诺保本保收益"),
        Source(id="reg_wm_sales", name="《商业银行理财业务监督管理办法》", kind="regulation", as_of="2018",
               note="理财产品销售文件须提示\"理财非存款、产品有风险、投资须谨慎\""),
        Source(id="param_rate", name="一年期定期存款参考利率", kind="parameter",
               note=f"演示参数 {REF_DEPOSIT_RATE:.1%}，正式版按实际挂牌利率更新"),
    ]
    return {s.id: s for s in sources}
