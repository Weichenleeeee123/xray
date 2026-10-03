"""测试用临时目录存案卷和模型录音，并关掉模型调用：测试不依赖网络和 Key。"""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="xray-test-")
os.environ["XRAY_CASES_DIR"] = os.path.join(_tmp, "cases")
os.environ["XRAY_DEMO_PREBUILT_DIR"] = os.path.join(_tmp, "demo_prebuilt")  # 本机生成的预制示例不影响测试
os.environ["XRAY_CACHE_DIR"] = os.path.join(_tmp, "cache")
os.environ["XRAY_REVIEWS_DIR"] = os.path.join(_tmp, "reviews")
os.environ["XRAY_RUNS_DIR"] = os.path.join(_tmp, "runs")
os.environ["XRAY_LLM_MODE"] = "off"
os.environ["XRAY_WEB_DISCOVERY"] = "0"  # legacy baseline; discovery tests explicitly enable fake services
os.environ["XRAY_WEB_DISCOVERY_LLM"] = "0"
os.environ["XRAY_COMMERCIAL"] = ""  # 商业接口按次计费，测试绝不调用
os.environ["XRAY_AMAC_DETAIL"] = "0"  # 不联网取中基协详情页
os.environ["XRAY_CNINFO"] = "0"  # 巨潮也联网，测试不查
for _quota in ("XRAY_QUOTA_GUEST", "XRAY_QUOTA_IP", "XRAY_QUOTA_ACCOUNT"):
    os.environ[_quota] = "0"  # 每日限额另有专门的测试；其余测试不受它影响
# Keep an explicit empty value so config._load_env cannot restore a real local key.
os.environ["XRAY_RESEND_KEY"] = ""
