from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Literal, Mapping, TypeVar, Type
import httpx
from pydantic import BaseModel, ValidationError

from .io import canonical_json, sha256_text, utc_now

T = TypeVar("T", bound=BaseModel)
NormalizedFinishReason = Literal[
    "complete", "length", "tool_call", "content_filter", "unknown"
]
ANTHROPIC_STRUCTURED_OUTPUT_TOOL_NAME = "submit_structured_response"
OPENAI_UNSUPPORTED_STRICT_SCHEMA_KEYWORDS = frozenset(
    {
        "allOf",
        "not",
        "dependentRequired",
        "dependentSchemas",
        "if",
        "then",
        "else",
    }
)


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
    provider_finish_reason: str | None = None
    normalized_finish_reason: NormalizedFinishReason = "unknown"


def normalize_provider_finish_reason(
    raw_response: Mapping[str, Any],
) -> tuple[str | None, NormalizedFinishReason]:
    """Extract and normalize OpenAI-compatible or Anthropic finish metadata."""

    provider_reason: str | None = None
    choices = raw_response.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
        raw_reason = choices[0].get("finish_reason")
        if raw_reason is not None:
            provider_reason = str(raw_reason)
    elif raw_response.get("stop_reason") is not None:
        provider_reason = str(raw_response.get("stop_reason"))

    if provider_reason is None or not provider_reason.strip():
        return provider_reason, "unknown"
    normalized = provider_reason.strip().casefold()
    if normalized in {"stop", "end_turn", "stop_sequence"}:
        return provider_reason, "complete"
    if normalized in {"length", "max_tokens", "model_context_window_exceeded"}:
        return provider_reason, "length"
    if normalized in {"tool_calls", "tool_call", "function_call", "tool_use"}:
        return provider_reason, "tool_call"
    if normalized in {"content_filter", "refusal"}:
        return provider_reason, "content_filter"
    return provider_reason, "unknown"


class ProviderRequestError(RuntimeError):
    """A deterministic provider-side client error that must not be retried."""

    def __init__(self, *, status_code: int, detail: str, schema_mode: bool):
        self.status_code = int(status_code)
        self.detail = str(detail)
        self.schema_mode = bool(schema_mode)
        mode = "schema mode " if self.schema_mode else ""
        super().__init__(f"{mode}HTTP {self.status_code}: {self.detail}")


class StructuredOutputValidationError(RuntimeError):
    """Preserve a paid provider response rejected by local semantic validation."""

    def __init__(
        self,
        *,
        call: CallResult,
        parsed_payload: Any,
        response_schema: Type[BaseModel],
        validation_error: ValidationError,
    ) -> None:
        self.call = call
        self.parsed_payload = parsed_payload
        self.response_schema = response_schema
        self.validation_errors = json.loads(
            json.dumps(
                validation_error.errors(
                    include_url=False,
                    include_context=True,
                    include_input=False,
                ),
                default=str,
            )
        )
        super().__init__(
            f"{response_schema.__name__} semantic validation failed after a "
            f"successful provider response: {validation_error}"
        )


def require_reported_usage(
    usage: Mapping[str, Any] | None, *, stage: str
) -> dict[str, int]:
    """Return normalized provider usage or fail closed on absent accounting."""

    raw = dict(usage or {})
    required = ("prompt_tokens", "completion_tokens", "total_tokens")
    try:
        normalized = {key: int(raw[key]) for key in required}
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"{stage} provider reported usage is missing or invalid") from exc
    if normalized["prompt_tokens"] <= 0 or normalized["completion_tokens"] <= 0:
        raise RuntimeError(
            f"{stage} provider reported usage must contain positive prompt/completion tokens"
        )
    if normalized["total_tokens"] != (
        normalized["prompt_tokens"] + normalized["completion_tokens"]
    ):
        raise RuntimeError(
            f"{stage} provider reported total_tokens is internally inconsistent"
        )
    return normalized


def openai_strict_json_schema(response_schema: Type[BaseModel]) -> dict[str, Any]:
    """Return a locally validated OpenAI Structured Outputs schema.

    OpenAI strict schemas require every declared object property to be listed
    in ``required`` and every object to forbid additional properties.  Reject
    incompatible Pydantic schemas before an HTTP attempt instead of paying for
    a deterministic provider-side 400.  Post-hoc Pydantic validation remains
    authoritative for value constraints and model validators.
    """

    schema = response_schema.model_json_schema()
    if schema.get("type") != "object" or not isinstance(
        schema.get("properties"), Mapping
    ):
        raise ValueError(
            f"{response_schema.__name__} strict schema root must be an object"
        )

    def visit(node: Any, path: str) -> None:
        if isinstance(node, list):
            for index, item in enumerate(node):
                visit(item, f"{path}[{index}]")
            return
        if not isinstance(node, dict):
            return
        unsupported = sorted(OPENAI_UNSUPPORTED_STRICT_SCHEMA_KEYWORDS & set(node))
        if unsupported:
            raise ValueError(
                f"{response_schema.__name__} strict schema uses unsupported "
                f"keywords at {path}: {unsupported}"
            )
        if "default" in node:
            raise ValueError(
                f"{response_schema.__name__} strict schema contains a default "
                f"at {path}; generated fields must be explicit"
            )
        if node.get("type") == "object" or "properties" in node:
            properties = node.get("properties")
            if not isinstance(properties, dict):
                raise ValueError(
                    f"{response_schema.__name__} strict object at {path} must "
                    "declare properties"
                )
            if node.get("additionalProperties") is not False:
                raise ValueError(
                    f"{response_schema.__name__} strict object at {path} must "
                    "set additionalProperties=false"
                )
            required = node.get("required")
            if (
                not isinstance(required, list)
                or len(required) != len(set(required))
                or set(required) != set(properties)
            ):
                raise ValueError(
                    f"{response_schema.__name__} strict object at {path} must "
                    "list every property exactly once in required"
                )
        for key, value in node.items():
            visit(value, f"{path}.{key}")

    visit(schema, "$")
    return schema


def _provider_error_summary(response: httpx.Response) -> str:
    """Extract a bounded structured provider error without logging prompts."""

    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError):
        return "provider returned no structured error detail"
    if not isinstance(body, Mapping):
        return "provider returned no structured error detail"
    raw_error = body.get("error", body)
    if not isinstance(raw_error, Mapping):
        return "provider returned no structured error detail"
    parts: list[str] = []
    for key in ("message", "type", "param", "code"):
        value = raw_error.get(key)
        if value is not None and str(value).strip():
            cleaned = " ".join(str(value).split())[:1000]
            parts.append(f"{key}={cleaned}")
    return "; ".join(parts) or "provider returned no structured error detail"


def chat_request_payload(
    endpoint: Endpoint,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    seed: int | None,
    response_schema: Type[BaseModel] | None,
) -> dict[str, Any]:
    """Build the exact initial provider payload used for cost/provenance hashes."""

    if "anthropic.com" in endpoint.base_url:
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        non_system = [m for m in messages if m["role"] != "system"]
        payload: dict[str, Any] = {
            "model": endpoint.model,
            "messages": non_system,
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if response_schema is not None:
            payload["tools"] = [
                {
                    "name": ANTHROPIC_STRUCTURED_OUTPUT_TOOL_NAME,
                    "description": (
                        "Return the evaluator result using the required strict schema."
                    ),
                    "input_schema": response_schema.model_json_schema(),
                }
            ]
            payload["tool_choice"] = {
                "type": "tool",
                "name": ANTHROPIC_STRUCTURED_OUTPUT_TOOL_NAME,
            }
        return payload
    payload = {
        "model": endpoint.model,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }
    if seed is not None:
        payload["seed"] = int(seed)
    if response_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": response_schema.__name__,
                "strict": True,
                "schema": openai_strict_json_schema(response_schema),
            },
        }
    return payload


def request_payload_has_schema(payload: Mapping[str, Any]) -> bool:
    """Recognize the exact OpenAI or Anthropic structured-output contract."""

    response_format = payload.get("response_format")
    if isinstance(response_format, Mapping):
        json_schema = response_format.get("json_schema")
        if (
            response_format.get("type") == "json_schema"
            and isinstance(json_schema, Mapping)
            and isinstance(json_schema.get("schema"), Mapping)
        ):
            return True
    tools = payload.get("tools")
    tool_choice = payload.get("tool_choice")
    if not isinstance(tools, list) or not isinstance(tool_choice, Mapping):
        return False
    forced_name = str(tool_choice.get("name") or "")
    return bool(
        tool_choice.get("type") == "tool"
        and forced_name
        and any(
            isinstance(tool, Mapping)
            and tool.get("name") == forced_name
            and isinstance(tool.get("input_schema"), Mapping)
            for tool in tools
        )
    )


class OpenAICompatibleClient:
    """Small fail-closed OpenAI-compatible chat client.

    It does not depend on a vendor SDK.  Requested JSON schema mode is
    fail-closed: a provider may not silently downgrade a frozen structured
    request to schema-less JSON.
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
        payload = chat_request_payload(
            self.endpoint,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            seed=seed,
            response_schema=response_schema,
        )
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
                # Deterministic client errors are not fixed by retries.  Retain
                # the frozen schema payload and surface the provider's bounded
                # structured error instead of silently issuing a schema-less
                # request with a different hash.
                if 400 <= response.status_code < 500:
                    raise ProviderRequestError(
                        status_code=response.status_code,
                        detail=_provider_error_summary(response),
                        schema_mode="response_format" in payload,
                    )
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
                provider_finish_reason, normalized_finish_reason = (
                    normalize_provider_finish_reason(body)
                )
                call = CallResult(
                    text=text.strip(),
                    raw_response=body,
                    usage=usage,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    request_hash=request_hash,
                    provider_finish_reason=provider_finish_reason,
                    normalized_finish_reason=normalized_finish_reason,
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
                try:
                    parsed = response_schema.model_validate(parsed_obj)
                except ValidationError as exc:
                    raise StructuredOutputValidationError(
                        call=call,
                        parsed_payload=parsed_obj,
                        response_schema=response_schema,
                        validation_error=exc,
                    ) from exc
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
        payload = chat_request_payload(
            self.endpoint,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            seed=seed,
            response_schema=response_schema,
        )
        request_hash = sha256_text(canonical_json(payload))
        errors: list[str] = []
        for attempt in range(1, retries + 1):
            started = time.perf_counter()
            try:
                response = self._client.post("/v1/messages", json=payload)
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    raise ProviderRequestError(
                        status_code=response.status_code,
                        detail=_provider_error_summary(response),
                        schema_mode=response_schema is not None,
                    )
                response.raise_for_status()
                body = response.json()
                content = body["content"]
                parsed_obj = None
                if response_schema is not None:
                    tool_blocks = [
                        block
                        for block in content
                        if block.get("type") == "tool_use"
                        and block.get("name")
                        == ANTHROPIC_STRUCTURED_OUTPUT_TOOL_NAME
                    ]
                    if len(tool_blocks) != 1:
                        raise ValueError(
                            "Anthropic structured response must contain exactly one "
                            "required tool_use block"
                        )
                    parsed_obj = tool_blocks[0].get("input")
                    text = canonical_json(parsed_obj)
                else:
                    text_blocks = [
                        block.get("text")
                        for block in content
                        if block.get("type") == "text"
                    ]
                    text = "\n".join(
                        value for value in text_blocks if isinstance(value, str)
                    ).strip()
                    if not text:
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
                provider_finish_reason, normalized_finish_reason = (
                    normalize_provider_finish_reason(body)
                )
                call = CallResult(
                    text=text.strip(),
                    raw_response=body,
                    usage=usage,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    request_hash=request_hash,
                    provider_finish_reason=provider_finish_reason,
                    normalized_finish_reason=normalized_finish_reason,
                )
                if response_schema is None:
                    return call, None
                try:
                    parsed = response_schema.model_validate(parsed_obj)
                except ValidationError as exc:
                    raise StructuredOutputValidationError(
                        call=call,
                        parsed_payload=parsed_obj,
                        response_schema=response_schema,
                        validation_error=exc,
                    ) from exc
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
        "provider_finish_reason": result.provider_finish_reason if result else None,
        "normalized_finish_reason": (
            result.normalized_finish_reason if result else None
        ),
        "completion_truncated": (
            result.normalized_finish_reason == "length" if result else None
        ),
        "validated": parsed.model_dump(mode="json") if parsed else None,
        "usage": result.usage if result else None,
        "latency_ms": result.latency_ms if result else None,
        "error": error,
    }
