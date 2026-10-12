#!/usr/bin/env python3
"""LLM 客户端：OpenAI 兼容端点调用 + 请求级缓存。

设计约束（见 SKILL.md 的 LLM 集成说明）：
  - 仅用标准库，不新增第三方依赖；
  - 只做「文本进、结构化 JSON 出」，不接触文件读写；
  - 所有请求按 (model, prompt_version, 输入) 缓存到磁盘，重跑不重复调用；
  - 网络/解析失败按次数退避重试，最终失败抛 LLMError 由调用方降级处理。

配置全部通过环境变量注入，密钥不落盘（不读配置文件）：
  ANONYMIZE_LLM_ENDPOINT    必填，OpenAI 兼容的 /chat/completions 地址
  ANONYMIZE_LLM_MODEL       必填，模型名
  ANONYMIZE_LLM_API_KEY     必填，密钥；未设置时回退读 DEEPSEEK_API_KEY
  ANONYMIZE_LLM_TIMEOUT     可选，单次请求超时秒数，默认 60
  ANONYMIZE_LLM_MAX_RETRIES 可选，失败重试次数，默认 2
  ANONYMIZE_LLM_MAX_TOKENS  可选，单次响应上限，默认 4096
  ANONYMIZE_LLM_TEMPERATURE 可选，采样温度，默认 0
  ANONYMIZE_LLM_CACHE_DIR   可选，请求缓存目录，默认 .llm-cache

优先级：显式传参（CLI 覆盖）> 环境变量 > 默认值。
密钥永不写日志、不进报告、不进缓存；打印时一律经 mask_key() 遮蔽。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

# 提示词版本：任何影响判定的提示词改动都必须递增，否则缓存会返回旧结果。
PROMPT_VERSION = "terms-review-v1"

ENV_PREFIX = "ANONYMIZE_LLM_"
FALLBACK_API_KEY_ENV = "DEEPSEEK_API_KEY"


class LLMError(RuntimeError):
    """配置、调用或解析失败（重试已耗尽）。"""


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(ENV_PREFIX + name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise LLMError(f"环境变量 {ENV_PREFIX + name} 不是合法数字: {raw!r}") from exc


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(ENV_PREFIX + name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise LLMError(f"环境变量 {ENV_PREFIX + name} 不是合法整数: {raw!r}") from exc


def mask_key(key: str) -> str:
    """遮蔽密钥，用于日志与配置摘要。绝不返回完整密钥。"""
    key = (key or "").strip()
    if not key:
        return "（未设置）"
    if len(key) <= 6:
        return "***"
    return f"{key[:3]}***"


@dataclass
class LLMConfig:
    endpoint: str = ""
    model: str = ""
    api_key: str = ""
    timeout_seconds: float = 120.0
    max_retries: int = 2
    retry_backoff_seconds: float = 2.0
    max_tokens: int = 4096
    temperature: float = 0.0
    cache_dir: str = ".llm-cache"
    use_json_response_format: bool = False
    # 透传到请求体的额外参数；推理模型建议 {"enable_thinking": false}
    extra_body: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, overrides: dict[str, Any] | None = None) -> "LLMConfig":
        """从环境变量构造配置；overrides 中非 None 的项覆盖环境变量。"""
        env = os.environ
        raw_extra = env.get(ENV_PREFIX + "EXTRA_BODY", "").strip()
        extra: dict = {}
        if raw_extra:
            try:
                parsed = json.loads(raw_extra)
            except json.JSONDecodeError as exc:
                raise LLMError(f"环境变量 {ENV_PREFIX}EXTRA_BODY 不是合法 JSON: {exc}") from exc
            if not isinstance(parsed, dict):
                raise LLMError(f"环境变量 {ENV_PREFIX}EXTRA_BODY 必须是 JSON 对象")
            extra = parsed
        cfg = cls(
            endpoint=env.get(ENV_PREFIX + "ENDPOINT", "").strip(),
            model=env.get(ENV_PREFIX + "MODEL", "").strip(),
            api_key=(
                env.get(ENV_PREFIX + "API_KEY", "").strip()
                or env.get(FALLBACK_API_KEY_ENV, "").strip()
            ),
            timeout_seconds=_env_float("TIMEOUT", 120.0),
            max_retries=_env_int("MAX_RETRIES", 2),
            max_tokens=_env_int("MAX_TOKENS", 4096),
            temperature=_env_float("TEMPERATURE", 0.0),
            cache_dir=env.get(ENV_PREFIX + "CACHE_DIR", ".llm-cache").strip() or ".llm-cache",
            extra_body=extra,
        )
        for key, value in (overrides or {}).items():
            if value is not None:
                if key not in cls.__dataclass_fields__:  # type: ignore[attr-defined]
                    raise LLMError(f"未知配置项: {key}")
                setattr(cfg, key, value)
        return cfg

    def missing(self) -> list[str]:
        """返回缺失的必填环境变量名，供调用方给出可操作的报错。"""
        missing: list[str] = []
        if not self.endpoint.strip():
            missing.append(ENV_PREFIX + "ENDPOINT")
        if not self.model.strip():
            missing.append(ENV_PREFIX + "MODEL")
        if not self.api_key.strip():
            missing.append(f"{ENV_PREFIX}API_KEY（或 {FALLBACK_API_KEY_ENV}）")
        return missing

    def validate(self) -> None:
        missing = self.missing()
        if missing:
            raise LLMError("缺少必要配置，请设置环境变量：" + "、".join(missing))

    def summary(self) -> str:
        """配置摘要（含遮蔽后的密钥），可安全打印。"""
        host = urlsplit(self.endpoint).netloc or self.endpoint
        extra = f" extra_body={json.dumps(self.extra_body, ensure_ascii=False)}" if self.extra_body else ""
        return (
            f"endpoint={host} model={self.model} api_key={mask_key(self.api_key)} "
            f"cache_dir={self.cache_dir} timeout={self.timeout_seconds}s "
            f"max_retries={self.max_retries} max_tokens={self.max_tokens}{extra}"
        )


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
    if config.extra_body:
        body.update(config.extra_body)
    req = urllib.request.Request(
        config.endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=config.timeout_seconds) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        # 出错信息可能回显请求内容，抛出前做一次密钥遮蔽
        if config.api_key:
            detail = detail.replace(config.api_key, mask_key(config.api_key))
        raise LLMError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"网络错误: {exc.reason}") from exc
    payload = json.loads(raw)
    try:
        choice = payload["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"响应结构不符合 OpenAI 兼容格式: {raw[:300]}") from exc
    if not (content or "").strip():
        # 典型原因：推理模型把 max_tokens 全用在思考上，导致没有正文输出
        usage = payload.get("usage", {}) or {}
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        finish = choice.get("finish_reason")
        detail = f"finish_reason={finish}"
        if usage.get("completion_tokens") is not None:
            detail += f", completion_tokens={usage.get('completion_tokens')}"
        if reasoning is not None:
            detail += f", reasoning_tokens={reasoning}"
        hint = ""
        if finish == "length" or (reasoning and usage.get("completion_tokens") == reasoning):
            hint = (
                "；输出被推理内容占满。若是推理模型，可设置 "
                "ANONYMIZE_LLM_EXTRA_BODY='{\"enable_thinking\": false}' 关闭思考，"
                "或调大 ANONYMIZE_LLM_MAX_TOKENS、调小批大小"
            )
        raise LLMError(f"模型返回空 content（{detail}）{hint}")
    return content


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
    overrides: dict[str, Any] | None = None,
    transport: Callable[[LLMConfig, str, str], str] | None = None,
) -> LLMClient:
    config = LLMConfig.from_env(overrides)
    config.validate()
    return LLMClient(config, transport=transport)
