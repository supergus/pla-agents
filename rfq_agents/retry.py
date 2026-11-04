"""Retry policy: exponential backoff with full jitter, max attempts, retryable vs fatal errors,
plus failure-injection hooks used by tests and the CLI's --inject-failure."""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from typing import Callable


class ToolError(Exception):
    retryable = False


class RetryableError(ToolError):
    """Transient: timeouts, rate limits, 5xx, malformed model output. Safe to try again."""
    retryable = True


class FatalError(ToolError):
    """Will not get better by retrying (bad input, contract violation). Becomes a blocker Issue."""
    retryable = False


class InjectedCrash(BaseException):
    """Simulates the process dying mid-run. BaseException so nothing in the PLA catches it."""


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, ToolError):
        return exc.retryable
    return isinstance(exc, (TimeoutError, ConnectionError))


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0
    jitter: bool = True
    sleep: Callable[[float], None] = field(default=None, repr=False)
    rng: random.Random = field(default_factory=random.Random, repr=False)

    def delay(self, attempt: int) -> float:
        """Delay before attempt `attempt + 1` (attempt is 1-based). Full jitter: U(0, cap)."""
        cap = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
        return self.rng.uniform(0, cap) if self.jitter else cap

    def wait(self, attempt: int) -> float:
        d = self.delay(attempt)
        if self.sleep is not None:
            self.sleep(d)
        else:
            import time
            time.sleep(d)
        return d


def idempotency_key(run_id: str, step: str, inputs: dict) -> str:
    h = hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return f"{run_id}:{step}:{h}"


@dataclass
class FailureInjector:
    """fail[tool] = n -> the first n attempts of `tool` raise (RetryableError, or FatalError if tool in fatal).
    crash_after = tool -> after `tool` succeeds and is checkpointed, raise InjectedCrash once."""
    fail: dict[str, int] = field(default_factory=dict)
    fatal: set[str] = field(default_factory=set)
    crash_after: str | None = None
    crash_before: str | None = None
    calls: dict[str, int] = field(default_factory=dict)

    @classmethod
    def parse(cls, specs: list[str] | None) -> "FailureInjector":
        inj = cls()
        for s in specs or []:
            name, _, n = s.partition(":")
            if n == "fatal":
                inj.fail[name] = 1; inj.fatal.add(name)
            elif n == "crash":
                inj.crash_after = name
            else:
                inj.fail[name] = int(n or 1)
        return inj

    def before(self, tool: str, attempt: int) -> None:
        self.calls[tool] = self.calls.get(tool, 0) + 1
        if self.crash_before == tool:
            self.crash_before = None
            raise InjectedCrash(f"injected crash during {tool}")
        if self.fail.get(tool, 0) > 0:
            self.fail[tool] -= 1
            if tool in self.fatal:
                raise FatalError(f"injected fatal failure in {tool}")
            raise RetryableError(f"injected transient failure in {tool} (attempt {attempt})")

    def after(self, tool: str) -> None:
        if self.crash_after == tool:
            self.crash_after = None
            raise InjectedCrash(f"injected crash after {tool}")
