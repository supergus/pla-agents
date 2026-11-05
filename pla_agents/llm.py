"""Pluggable LLM interface for the agentic tools.

- `CannedLLMClient`: offline, deterministic; used by tests, CI and the default CLI.
- `WorkersAIClient`: Cloudflare Workers AI REST API (Llama 3.3 70B). Reads CLOUDFLARE_API_TOKEN and
  CLOUDFLARE_ACCOUNT_ID from the environment; never hard-coded; never called in tests.

Every response is treated as an untrusted proposal: tools validate it (JSON schema, then SHACL)
before anything reaches the program graph.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Protocol

from .retry import FatalError, RetryableError

DEFAULT_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"


class LLMClient(Protocol):
    name: str

    def complete_json(self, task: str, system: str, user: str, schema: dict) -> dict: ...


class CannedLLMClient:
    """Returns fixed responses per task. A response may be a dict or a callable(user_text) -> dict."""
    name = "canned"

    def __init__(self, responses: dict[str, Any] | None = None):
        from .canned import DEFAULT_RESPONSES
        self.responses = {**DEFAULT_RESPONSES, **(responses or {})}
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, task: str, system: str, user: str, schema: dict) -> dict:
        self.calls.append((task, user))
        if task not in self.responses:
            raise FatalError(f"canned LLM has no response for task {task!r}")
        r = self.responses[task]
        return json.loads(json.dumps(r(user) if callable(r) else r))


class WorkersAIClient:
    """Cloudflare Workers AI over HTTPS: POST /accounts/{id}/ai/run/{model}.
    429/5xx/timeouts -> RetryableError; other 4xx -> FatalError."""
    name = "workers-ai"

    def __init__(self, model: str = DEFAULT_MODEL, account_id: str | None = None, api_token: str | None = None,
                 timeout: float = 60.0, opener: Callable | None = None, max_tokens: int = 1024):
        self.model = model
        self.account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        self._token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN")
        if not self.account_id or not self._token:
            raise FatalError("WorkersAIClient needs CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN in the environment")
        self.timeout = timeout
        self.max_tokens = max_tokens
        self._open = opener or urllib.request.urlopen

    def url(self) -> str:
        return f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model}"

    def request_body(self, system: str, user: str, schema: dict) -> dict:
        return {
            "messages": [{"role": "system", "content": system + "\nReply with JSON only."},
                         {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": schema},
            "max_tokens": self.max_tokens,
            "temperature": 0,
        }

    def complete_json(self, task: str, system: str, user: str, schema: dict) -> dict:
        req = urllib.request.Request(self.url(), data=json.dumps(self.request_body(system, user, schema)).encode(),
                                     headers={"Authorization": f"Bearer {self._token}",
                                              "Content-Type": "application/json"}, method="POST")
        try:
            with self._open(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                raise RetryableError(f"Workers AI HTTP {e.code}") from e
            raise FatalError(f"Workers AI HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise RetryableError(f"Workers AI unreachable: {e}") from e
        return parse_workers_ai_payload(payload)


def parse_workers_ai_payload(payload: dict) -> dict:
    if not payload.get("success", True):
        raise RetryableError(f"Workers AI error: {payload.get('errors')}")
    resp = (payload.get("result") or {}).get("response")
    if isinstance(resp, dict):
        return resp
    if isinstance(resp, str):
        s = resp.strip()
        if s.startswith("```"):
            s = s.strip("`").removeprefix("json").strip()
        try:
            out = json.loads(s)
        except json.JSONDecodeError as e:
            raise RetryableError("model returned non-JSON output") from e
        if isinstance(out, dict):
            return out
    raise RetryableError("model returned no JSON object")


def client_from_name(name: str) -> LLMClient:
    if name == "canned":
        return CannedLLMClient()
    if name == "workers-ai":
        return WorkersAIClient(model=os.environ.get("PLA_AGENTS_MODEL", DEFAULT_MODEL))
    raise ValueError(f"unknown LLM client {name!r} (canned | workers-ai)")
