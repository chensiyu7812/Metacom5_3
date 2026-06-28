from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, TypeVar, Type
import httpx
from pydantic import BaseModel, ValidationError

from .io import canonical_json, sha256_text, utc_now

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Endpoint:
    base_url: str
    model: str
    api_key_env: str
    timeout_seconds: float = 180.0
    # A human-declared model family is required for confirmatory runs.  Model
    # aliases and vendor gateways are not reliable indicators of independence.
    family: str | None = None

    @property
    def api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "")
        if not key:
            raise RuntimeError(f"Environment variable {self.api_key_env} is not set")
        return key


@dataclass
class CallResult:
    text: str
    raw_response: dict[str, Any]
    usage: dict[str, int]
    latency_ms: float
    request_hash: str


class OpenAICompatibleClient:
    """Small fail-closed OpenAI-compatible chat client.

    It does not depend on a vendor SDK.  JSON schema mode is attempted only
    when requested; endpoints that do not support it can use strict prompt JSON
    with parse/validation retries.
    """

    def __init__(self, endpoint: Endpoint):
        self.endpoint = endpoint
        self._chat_path = self._resolve_chat_path(endpoint.base_url)
        self._client = httpx.Client(
            base_url=endpoint.base_url.rstrip("/"),
            timeout=endpoint.timeout_seconds,
            headers={
                "Authorization": f"Bearer {endpoint.api_key}",
                "Content-Type": "application/json",
            },
        )

    @staticmethod
    def _resolve_chat_path(base_url: str) -> str:
        """Return the chat-completions path for root or prefixed base URLs.

        OpenAI/NVIDIA often use a root base URL plus /v1/chat/completions.
        Some OpenAI-compatible providers document a prefixed base URL, e.g.
        Gemini's /v1beta/openai, where appending another /v1 would break.
        """
        normalized = base_url.rstrip("/")
        if normalized.endswith("/v1") or normalized.endswith("/openai"):
            return "/chat/completions"
        return "/v1/chat/completions"

    def close(self) -> None:
        self._client.close()

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 512,
        seed: int | None = None,
        response_schema: Type[T] | None = None,
        retries: int = 3,
    ) -> tuple[CallResult, T | None]:
        payload: dict[str, Any] = {
            "model": self.endpoint.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if seed is not None:
            payload["seed"] = seed
        if response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.__name__,
                    "strict": True,
                    "schema": response_schema.model_json_schema(),
                },
            }
        request_hash = sha256_text(canonical_json(payload))
        errors: list[str] = []
        for attempt in range(1, retries + 1):
            started = time.perf_counter()
            try:
                response = self._client.post(self._chat_path, json=payload)
                # 429 Rate limit: back off with longer wait and retry.
                if response.status_code == 429:
                    retry_after = int(response.headers.get("retry-after", "0") or 0)
                    wait = max(retry_after, min(30 * attempt, 120))
                    errors.append(f"attempt {attempt}: 429 rate-limited, waiting {wait}s")
                    if attempt < retries:
                        time.sleep(wait)
                    continue
                # Some compatible endpoints reject response_format. Retry without
                # it, while retaining strict post-hoc validation.
                if response.status_code >= 400 and "response_format" in payload:
                    errors.append(f"attempt {attempt}: schema mode HTTP {response.status_code}")
                    payload = dict(payload)
                    payload.pop("response_format", None)
                    request_hash = sha256_text(canonical_json(payload))
                    continue
                response.raise_for_status()
                body = response.json()
                text = body["choices"][0]["message"]["content"]
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("empty model response")
                usage_raw = body.get("usage") or {}
                usage = {
                    "prompt_tokens": int(usage_raw.get("prompt_tokens") or 0),
                    "completion_tokens": int(usage_raw.get("completion_tokens") or 0),
                    "total_tokens": int(usage_raw.get("total_tokens") or 0),
                }
                call = CallResult(
                    text=text.strip(),
                    raw_response=body,
                    usage=usage,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    request_hash=request_hash,
                )
                if response_schema is None:
                    return call, None
                try:
                    parsed_obj = json.loads(text)
                except json.JSONDecodeError:
                    start, end = text.find("{"), text.rfind("}")
                    if start < 0 or end <= start:
                        raise ValueError("response is not valid JSON")
                    parsed_obj = json.loads(text[start : end + 1])
                parsed = response_schema.model_validate(parsed_obj)
                return call, parsed
            except (httpx.HTTPError, KeyError, IndexError, ValueError, ValidationError, json.JSONDecodeError) as exc:
                errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
                if attempt == retries:
                    break
                time.sleep(min(2 ** (attempt - 1), 8))
        raise RuntimeError("API call failed after strict retries: " + " | ".join(errors))


class AnthropicClient:
    """Minimal Anthropic Messages API client (claude-* models).

    Anthropic's native API is NOT OpenAI-compatible, so we need a separate
    client.  The interface mirrors OpenAICompatibleClient so callers can swap
    transparently.
    """

    BASE_URL = "https://api.anthropic.com"
    API_VERSION = "2023-06-01"

    def __init__(self, endpoint: Endpoint):
        self.endpoint = endpoint
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            timeout=endpoint.timeout_seconds,
            headers={
                "x-api-key": endpoint.api_key,
                "anthropic-version": self.API_VERSION,
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 512,
        seed: int | None = None,
        response_schema: Type[T] | None = None,
        retries: int = 3,
    ) -> tuple[CallResult, T | None]:
        # Anthropic separates system from user/assistant messages
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        non_system = [m for m in messages if m["role"] != "system"]
        payload: dict[str, Any] = {
            "model": self.endpoint.model,
            "messages": non_system,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        request_hash = sha256_text(canonical_json(payload))
        errors: list[str] = []
        for attempt in range(1, retries + 1):
            started = time.perf_counter()
            try:
                response = self._client.post("/v1/messages", json=payload)
                response.raise_for_status()
                body = response.json()
                text = body["content"][0]["text"]
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("empty model response")
                usage_raw = body.get("usage") or {}
                usage = {
                    "prompt_tokens": int(usage_raw.get("input_tokens") or 0),
                    "completion_tokens": int(usage_raw.get("output_tokens") or 0),
                    "total_tokens": int(
                        (usage_raw.get("input_tokens") or 0)
                        + (usage_raw.get("output_tokens") or 0)
                    ),
                }
                call = CallResult(
                    text=text.strip(),
                    raw_response=body,
                    usage=usage,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    request_hash=request_hash,
                )
                if response_schema is None:
                    return call, None
                try:
                    parsed_obj = json.loads(text)
                except json.JSONDecodeError:
                    start, end = text.find("{"), text.rfind("}")
                    if start < 0 or end <= start:
                        raise ValueError("response is not valid JSON")
                    parsed_obj = json.loads(text[start : end + 1])
                parsed = response_schema.model_validate(parsed_obj)
                return call, parsed
            except (httpx.HTTPError, KeyError, IndexError, ValueError, ValidationError, json.JSONDecodeError) as exc:
                errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
                if attempt == retries:
                    break
                time.sleep(min(2 ** (attempt - 1), 8))
        raise RuntimeError("Anthropic API call failed after retries: " + " | ".join(errors))


def make_client(endpoint: Endpoint) -> OpenAICompatibleClient | AnthropicClient:
    """Return the appropriate client for the endpoint's base_url."""
    if "anthropic.com" in endpoint.base_url:
        return AnthropicClient(endpoint)
    return OpenAICompatibleClient(endpoint)


def request_log(
    *,
    stage: str,
    endpoint: Endpoint,
    messages: list[dict[str, str]],
    result: CallResult | None,
    parsed: BaseModel | None,
    error: str | None,
    prompt_hash: str,
    record_ids: dict[str, Any],
) -> dict[str, Any]:
    return {
        "timestamp": utc_now(),
        "stage": stage,
        **record_ids,
        "model": endpoint.model,
        "model_family": endpoint.family,
        "base_url": endpoint.base_url,
        "prompt_hash": prompt_hash,
        "messages_hash": sha256_text(canonical_json(messages)),
        "request_hash": result.request_hash if result else None,
        "raw_text": result.text if result else None,
        "raw_response": result.raw_response if result else None,
        "validated": parsed.model_dump(mode="json") if parsed else None,
        "usage": result.usage if result else None,
        "latency_ms": result.latency_ms if result else None,
        "error": error,
    }
