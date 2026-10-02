"""测试用临时目录存案卷和模型录音，并关掉模型调用：测试不依赖网络和 Key。"""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="xray-test-")
os.environ["XRAY_CASES_DIR"] = os.path.join(_tmp, "cases")
os.environ["XRAY_CACHE_DIR"] = os.path.join(_tmp, "cache")
os.environ["XRAY_LLM_MODE"] = "off"
os.environ["XRAY_COMMERCIAL"] = ""  # 商业接口按次计费，测试绝不调用
os.environ["XRAY_AMAC_DETAIL"] = "0"  # 不联网取中基协详情页
