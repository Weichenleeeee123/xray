"""模型网关：比赛的 Tokendance（OpenAI 兼容 chat completions），用 httpx 直接调。

- 每次成功的响应都录进 data/cache/，网关不通时自动回放，并在结果里标 mode="replay"、录制时间。
- chat_json：要求模型输出 JSON，用 Pydantic 校验；不合格就把错误告诉模型重试一次，再不行抛 LLMError，
  调用方退回规则或模板。
- 没配 Key 时 configured=False，所有调用直接走回放或报错，不会卡住演示。
"""
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app import config

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


@dataclass
class LLMReply:
    text: str
    mode: Literal["model", "replay"]
    recorded_at: str
    model: str


def parse_json(text: str) -> dict:
    """容忍 ```json 包裹和前后多余的话，取第一个 { 到最后一个 }。"""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("没有找到 JSON 对象")
    return json.loads(text[start:end + 1])


class LLM:
    def __init__(self, base_url: str = config.LLM_BASE_URL, api_key: str = config.LLM_API_KEY,
                 model: str = config.LLM_MODEL, vision_model: str = config.LLM_VISION_MODEL,
                 mode: str = config.LLM_MODE, cache_dir: Path = config.CACHE_DIR,
                 json_mode: bool = config.LLM_JSON_MODE, timeout: float = config.LLM_TIMEOUT):
        self.base_url, self.api_key, self.model, self.vision_model = base_url, api_key, model, vision_model
        self.mode, self.cache_dir, self.json_mode, self.timeout = mode, cache_dir, json_mode, timeout

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def status(self) -> dict:
        cached = len(list(self.cache_dir.glob("*.json"))) if self.cache_dir.exists() else 0
        host = re.sub(r"^https?://", "", self.base_url).split("/")[0] if self.base_url else None
        return {"configured": self.configured, "mode": self.mode, "model": self.model or None, "host": host,
                "cached_replies": cached}

    # ---------- 录音与回放 ----------

    def _key(self, model: str, messages: list, json_out: bool) -> str:
        blob = json.dumps({"model": model, "messages": messages, "json": json_out}, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]

    def _replay(self, key: str) -> LLMReply:
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            raise LLMError("模型网关不可用，也没有录好的响应")
        rec = json.loads(path.read_text(encoding="utf-8"))
        return LLMReply(text=rec["text"], mode="replay", recorded_at=rec["recorded_at"], model=rec["model"])

    def _record(self, key: str, reply: LLMReply) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / f"{key}.json").write_text(
            json.dumps({"text": reply.text, "recorded_at": reply.recorded_at, "model": reply.model}, ensure_ascii=False),
            encoding="utf-8")

    # ---------- 调用 ----------

    def _call(self, model: str, messages: list, json_out: bool, temperature: float) -> str:
        payload = {"model": model, "messages": messages, "temperature": temperature}
        if json_out and self.json_mode:
            payload["response_format"] = {"type": "json_object"}
        r = httpx.post(f"{self.base_url}/chat/completions", json=payload, timeout=self.timeout,
                       headers={"Authorization": f"Bearer {self.api_key}"})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def chat(self, messages: list, *, vision: bool = False, json_out: bool = False,
             temperature: float = 0.2) -> LLMReply:
        model = self.vision_model if vision else self.model
        key = self._key(model, messages, json_out)
        if self.mode == "off":
            raise LLMError("模型调用已关闭（XRAY_LLM_MODE=off）")
        if self.mode == "replay" or not self.configured:
            return self._replay(key)
        try:
            text = self._call(model, messages, json_out, temperature)
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            try:
                return self._replay(key)
            except LLMError:
                raise LLMError(f"模型网关调用失败：{type(e).__name__}") from e
        reply = LLMReply(text=text, mode="model", recorded_at=datetime.now().isoformat(timespec="seconds"), model=model)
        self._record(key, reply)
        return reply

    def chat_json(self, messages: list, schema: type[T], **kw) -> tuple[T, LLMReply]:
        reply = self.chat(messages, json_out=True, **kw)
        try:
            return schema.model_validate(parse_json(reply.text)), reply
        except (ValueError, ValidationError) as e:
            retry = messages + [{"role": "assistant", "content": reply.text},
                                {"role": "user", "content": f"上面的输出不符合要求（{str(e)[:200]}）。只输出符合要求的 JSON，不要别的文字。"}]
            reply = self.chat(retry, json_out=True, **kw)
            try:
                return schema.model_validate(parse_json(reply.text)), reply
            except (ValueError, ValidationError) as e2:
                raise LLMError(f"模型两次输出都不是合格的 JSON：{str(e2)[:120]}") from e2
