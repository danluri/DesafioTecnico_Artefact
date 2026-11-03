"""Tiny optional MCP-shaped seam without an MCP SDK or network transport."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .order import AuthorizedPrincipal
from .tools import ToolRegistry


@dataclass(frozen=True, slots=True)
class MCPResult:
    operation: str
    value: Any = None
    error: str | None = None


class MCPAdapter:
    """Expose only existing read-only tools; input cannot name imports, URLs, or commands."""

    SERVER_OWNED_ALLOWLIST = frozenset(
        ("search_catalog", "product_detail", "answer_policy", "order_status")
    )

    def __init__(self, tools: ToolRegistry, allowlist: tuple[str, ...] | None = None) -> None:
        self.tools = tools
        if allowlist is not None and frozenset(allowlist) != self.SERVER_OWNED_ALLOWLIST:
            raise ValueError("MCP allowlist is server-owned")
        self.allowlist = self.SERVER_OWNED_ALLOWLIST

    def call(
        self,
        operation: str,
        arguments: Mapping[str, Any],
        *,
        principal: AuthorizedPrincipal | None = None,
    ) -> MCPResult:
        if operation not in self.allowlist:
            return MCPResult(operation, error="unsupported operation")
        try:
            outcome = self.tools.execute(operation, arguments, principal=principal)
        except Exception:
            return MCPResult(operation, error="operation unavailable")
        return MCPResult(operation, outcome.value)
