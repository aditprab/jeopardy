from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - dependency may be installed after deploy
    OpenAI = None  # type: ignore[assignment]

try:
    from langsmith import wrappers as langsmith_wrappers
except ImportError:  # pragma: no cover - optional dependency in some environments
    langsmith_wrappers = None  # type: ignore[assignment]


@dataclass(frozen=True)
class AgentSpec:
    name: str
    version: str
    policy_version: str
    prompt_version: str


@dataclass(frozen=True)
class AgentUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class JsonSchemaRequest:
    system_prompt: str
    user_prompt: str
    schema_name: str
    schema: dict[str, Any]


@dataclass(frozen=True)
class JsonSchemaResponse:
    model: str
    response_id: str | None
    payload: dict[str, Any]
    usage: AgentUsage


def usage_from_response(resp: Any) -> AgentUsage:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return AgentUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", input_tokens + output_tokens) or 0)
    return AgentUsage(
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        total_tokens=total_tokens,
    )


class OpenAIJsonSchemaRunner:
    def __init__(
        self,
        *,
        default_model: str,
        model_env_var: str,
        timeout_env_var: str,
        default_timeout_ms: int,
        client: Any | None = None,
        api_key_env_var: str = "OPENAI_API_KEY",
    ):
        self.default_model = default_model
        self.model_env_var = model_env_var
        self.timeout_env_var = timeout_env_var
        self.default_timeout_ms = default_timeout_ms
        self.api_key_env_var = api_key_env_var
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if OpenAI is None:
            raise RuntimeError("openai package not installed")
        api_key = os.getenv(self.api_key_env_var)
        if not api_key:
            raise RuntimeError(f"{self.api_key_env_var} not configured")
        timeout_ms = int(os.getenv(self.timeout_env_var, str(self.default_timeout_ms)))
        client = OpenAI(api_key=api_key, timeout=timeout_ms / 1000.0)
        if (
            langsmith_wrappers is not None
            and os.getenv("LANGSMITH_TRACING", "").strip().lower() == "true"
        ):
            client = langsmith_wrappers.wrap_openai(client)
        self._client = client
        return self._client

    def resolve_model(self, model: str | None = None) -> str:
        return model or os.getenv(self.model_env_var, self.default_model)

    def run_json_schema(
        self,
        request: JsonSchemaRequest,
        *,
        model: str | None = None,
    ) -> JsonSchemaResponse:
        resolved_model = self.resolve_model(model)
        client = self._get_client()
        response = client.responses.create(
            model=resolved_model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": request.system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": request.user_prompt}],
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": request.schema_name,
                    "strict": True,
                    "schema": request.schema,
                }
            },
        )
        raw_text = getattr(response, "output_text", "") or ""
        payload = json.loads(raw_text)
        return JsonSchemaResponse(
            model=resolved_model,
            response_id=getattr(response, "id", None),
            payload=payload,
            usage=usage_from_response(response),
        )
