#!/usr/bin/env python3
"""LLM 客户端：OpenAI 兼容端点调用 + 请求级缓存。

设计约束（见 SKILL.md 的 LLM 集成说明）：
  - 仅用标准库，不新增第三方依赖；
  - 只做「文本进、结构化 JSON 出」，不接触文件读写；
  - 所有请求按 (model, prompt_version, 输入) 缓存到磁盘，重跑不重复调用；
  - 网络/解析失败按次数退避重试，最终失败抛 LLMError 由调用方降级处理。

配置来源优先级：
  显式 --llm-config 路径 > scripts/llm-config.json > ~/.config/anonymize-skill/llm-config.json
API key 优先级：配置文件 api_key > 环境变量 api_key_env。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

# 提示词版本：任何影响判定的提示词改动都必须递增，否则缓存会返回旧结果。
PROMPT_VERSION = "terms-review-v1"

DEFAULT_CONFIG_PATHS = (
    Path("scripts/llm-config.json"),
    Path.home() / ".config" / "anonymize-skill" / "llm-config.json",
)


class LLMError(RuntimeError):
    """调用或解析失败（已重试耗尽）。"""


@dataclass
class LLMConfig:
    endpoint: str = ""
    model: str = "deepseek-v41-flash"
    api_key: str = ""
    api_key_env: str = "DEEPSEEK_API_KEY"
    timeout_seconds: float = 60.0
    max_retries: int = 2
    retry_backoff_seconds: float = 2.0
    max_tokens: int = 4096
    temperature: float = 0.0
    cache_dir: str = ".llm-cache"
    use_json_response_format: bool = False

    def resolved_key(self) -> str:
        if self.api_key and self.api_key.strip():
            return self.api_key.strip()
        return os.environ.get(self.api_key_env, "").strip()

    @classmethod
    def load(cls, path: Path | None = None, overrides: dict[str, Any] | None = None) -> "LLMConfig":
        data: dict[str, Any] = {}
        candidates = (path,) if path is not None else DEFAULT_CONFIG_PATHS
        for cand in candidates:
            if cand and Path(cand).is_file():
                data = json.loads(Path(cand).read_text(encoding="utf-8"))
                break
        for key, value in (overrides or {}).items():
            if value is not None:
                data[key] = value
        allowed = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise LLMError(f"配置文件包含未知字段: {', '.join(unknown)}")
        return cls(**{k: v for k, v in data.items() if k in allowed})

    def validate(self) -> None:
        if not self.endpoint.strip():
            raise LLMError("未配置 endpoint：请在 llm-config.json 中填写 endpoint，或用 --llm-endpoint 指定")
        if not self.model.strip():
            raise LLMError("未配置 model")


class RequestCache:
    """按 key 把响应落盘的简单缓存。命中即不再发起网络请求。"""

    def __init__(self, cache_dir: str | Path):
        self.dir = Path(cache_dir)
        self.hits = 0
        self.misses = 0

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(self, key: str) -> Any | None:
        p = self._path(key)
        if p.is_file():
            try:
                self.hits += 1
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
        self.misses += 1
        return None

    def put(self, key: str, value: Any) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self._path(key).with_suffix(".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path(key))


def cache_key(model: str, prompt_version: str, payload: str) -> str:
    raw = f"{model}\x00{prompt_version}\x00{payload}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def extract_json(text: str) -> Any:
    """从模型输出中提取 JSON：容忍 ```json 围栏与前后说明文字。"""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMError("模型输出中找不到 JSON 对象")
    try:
        return json.loads(s[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"模型输出 JSON 解析失败: {exc}") from exc


def default_transport(config: LLMConfig, system: str, user: str) -> str:
    """默认 HTTP 传输：OpenAI 兼容 /chat/completions。"""
    body: dict[str, Any] = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "stream": False,
    }
    if config.use_json_response_format:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        config.endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.resolved_key()}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=config.timeout_seconds) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise LLMError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"网络错误: {exc.reason}") from exc
    payload = json.loads(raw)
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"响应结构不符合 OpenAI 兼容格式: {raw[:300]}") from exc


class LLMClient:
    """带缓存与重试的 JSON 对话客户端。

    transport 可注入（测试时传 stub，完全不联网）。
    """

    def __init__(
        self,
        config: LLMConfig,
        cache: RequestCache | None = None,
        transport: Callable[[LLMConfig, str, str], str] | None = None,
    ):
        self.config = config
        self.cache = cache if cache is not None else RequestCache(config.cache_dir)
        self._transport = transport or default_transport
        self.network_calls = 0

    def chat_json(self, system: str, user: str, prompt_version: str = PROMPT_VERSION) -> Any:
        key = cache_key(self.config.model, prompt_version, system + "\x00" + user)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            if attempt:
                time.sleep(self.config.retry_backoff_seconds * attempt)
            try:
                self.network_calls += 1
                text = self._transport(self.config, system, user)
                data = extract_json(text)
            except LLMError as exc:
                last_error = exc
                continue
            self.cache.put(key, data)
            return data
        raise LLMError(f"重试 {self.config.max_retries + 1} 次后仍失败: {last_error}")


def build_client(
    config_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
    transport: Callable[[LLMConfig, str, str], str] | None = None,
) -> LLMClient:
    config = LLMConfig.load(config_path, overrides)
    config.validate()
    return LLMClient(config, transport=transport)
