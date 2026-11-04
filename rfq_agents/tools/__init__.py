"""Tool registry. Importing this package registers every tool in REGISTRY by contract name."""
from . import agentic, deterministic  # noqa: F401  (registration side effects)
from .base import REGISTRY, IssueSpec, Tool, ToolContext, ToolResult

__all__ = ["REGISTRY", "IssueSpec", "Tool", "ToolContext", "ToolResult"]
