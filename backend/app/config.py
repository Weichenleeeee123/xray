import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FIXTURES_DIR = DATA_DIR / "fixtures"
LICENSE_CSV = DATA_DIR / "licensed_institutions.csv"
LICENSE_META = DATA_DIR / "licensed_institutions.meta.json"

# 演示参数：一年期定期存款参考利率。正式版应按实际挂牌利率更新，并在界面标注来源。
REF_DEPOSIT_RATE = float(os.getenv("XRAY_REF_DEPOSIT_RATE", "0.011"))
# 宣称收益超过定存多少倍时标为"要留意"
HIGH_RETURN_RATIO = 3.0
# 实缴低于认缴的这个比例，"注册资本 X 万"的说法算误导
LOW_PAID_RATIO = 0.1
# 成立不满多少个月，标为"成立时间短"
YOUNG_COMPANY_MONTHS = 24
