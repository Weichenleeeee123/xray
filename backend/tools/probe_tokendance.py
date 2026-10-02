"""Run with: python -m tools.probe_tokendance --capability text --live.

Only synthetic input is sent. Omitting --live performs zero network requests.
"""
import argparse
import base64
import io
import json
from datetime import datetime, timezone

from PIL import Image, ImageDraw
from pydantic import BaseModel, ConfigDict

from app.llm import LLM, LLMError


class ProbeJSON(BaseModel):
    model_config = ConfigDict(extra="forbid")
    penguin: bool
    number: int


def run_probe(llm: LLM, capability: str, *, live: bool = False) -> dict:
    result = {"capability": capability, "checked_at": datetime.now(timezone.utc).isoformat(),
              "status": "not_tested", "configured": llm.configured}
    if capability in {"search", "reader"}:
        return {**result, "status": "blocked_protocol", "note": "此模型探针未接搜索/阅读适配器；实际搜索见 app/sources/web.py，未用聊天充当联网"}
    if not live:
        return result
    if not llm.configured:
        return {**result, "status": "blocked_config"}
    if capability == "vision" and not llm.vision_model:
        return {**result, "status": "blocked_config", "note": "缺少视觉模型名称"}
    try:
        if capability == "text":
            reply = llm.chat([{"role": "user", "content": "中文连通测试，请只回答：企鹅"}],
                             temperature=0, cache_namespace="probe:text")
            passed = "企鹅" in reply.text
        elif capability == "json":
            out, reply = llm.chat_json([{"role": "user", "content": '输出 JSON：{"penguin":true,"number":123}'}],
                                      ProbeJSON, temperature=0, cache_namespace="probe:json")
            passed = out.penguin is True and out.number == 123
        elif capability == "vision":
            img = Image.new("RGB", (300, 90), "white")
            ImageDraw.Draw(img).text((15, 15), "PENGUIN 123", fill="black", font_size=30)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
            reply = llm.chat([{"role": "user", "content": [
                {"type": "text", "text": "逐字转录图中文字，不补充其他内容"},
                {"type": "image_url", "image_url": {"url": url}}]}],
                vision=True, temperature=0, cache_namespace="probe:vision")
            passed = "123" in reply.text and "PENGUIN" in reply.text.upper()
        else:
            return {**result, "status": "unsupported_probe"}
        return {**result, "status": ("tested" if passed else "content_mismatch") if reply.mode == "model" else "replay_only",
                "mode": reply.mode, "recorded_at": reply.recorded_at,
                "note": "合成输入连通测试，不代表真实材料识别质量已验收"}
    except LLMError as err:
        return {**result, "status": "failed", "error_code": err.code}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capability", choices=["text", "json", "vision", "search", "reader"], required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_probe(LLM(), args.capability, live=args.live), ensure_ascii=False))


if __name__ == "__main__":
    main()
