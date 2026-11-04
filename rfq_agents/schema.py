"""Minimal JSON-schema subset validator (type, properties, required, enum, minimum, maximum, items,
additionalProperties=false, minLength). Enough to gate LLM output without another dependency."""
from __future__ import annotations

from .retry import RetryableError

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


class SchemaError(RetryableError):
    """Model output that does not fit the contract. Retryable: a fresh sample may comply."""


def _type_ok(v, t) -> bool:
    if isinstance(t, list):
        return any(_type_ok(v, x) for x in t)
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(v, _TYPES[t])


def validate(v, schema: dict, path: str = "$") -> None:
    t = schema.get("type")
    if t and not _type_ok(v, t):
        raise SchemaError(f"{path}: expected {t}, got {type(v).__name__}")
    if "enum" in schema and v not in schema["enum"]:
        raise SchemaError(f"{path}: {v!r} not in {schema['enum']}")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if "minimum" in schema and v < schema["minimum"]:
            raise SchemaError(f"{path}: {v} < {schema['minimum']}")
        if "maximum" in schema and v > schema["maximum"]:
            raise SchemaError(f"{path}: {v} > {schema['maximum']}")
    if isinstance(v, str) and len(v) < schema.get("minLength", 0):
        raise SchemaError(f"{path}: string too short")
    if isinstance(v, dict):
        for k in schema.get("required", []):
            if k not in v:
                raise SchemaError(f"{path}: missing {k}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(v) - set(props)
            if extra:
                raise SchemaError(f"{path}: unexpected {sorted(extra)}")
        for k, sub in props.items():
            if k in v:
                validate(v[k], sub, f"{path}.{k}")
    if isinstance(v, list) and "items" in schema:
        if len(v) < schema.get("minItems", 0):
            raise SchemaError(f"{path}: too few items")
        for i, x in enumerate(v):
            validate(x, schema["items"], f"{path}[{i}]")
