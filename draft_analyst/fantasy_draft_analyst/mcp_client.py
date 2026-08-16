from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

from .http_json import HttpError, request_json


@dataclass
class McpClient:
    url: str
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1))
    initialized: bool = False
    tools_cache: dict[str, Any] | None = None

    def rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        payload = {"jsonrpc": "2.0", "id": next(self._ids), "method": method}
        if params is not None:
            payload["params"] = params
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        result = request_json("POST", self.url, headers=headers, body=payload, timeout=45)
        if isinstance(result, dict) and result.get("error"):
            raise HttpError(f"MCP {method} failed: {result['error']}")
        return result.get("result") if isinstance(result, dict) else result

    def initialize(self) -> None:
        if self.initialized:
            return
        self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "fantasy-draft-analyst", "version": "0.1.0"},
            },
        )
        try:
            self.rpc("notifications/initialized")
        except Exception:
            pass
        self.initialized = True

    def list_tools(self) -> dict[str, Any]:
        self.initialize()
        if self.tools_cache is None:
            self.tools_cache = self.rpc("tools/list") or {}
        return self.tools_cache

    def has_tool(self, name: str) -> bool:
        tools = self.list_tools().get("tools", [])
        return any(tool.get("name") == name for tool in tools)

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        self.initialize()
        result = self.rpc("tools/call", {"name": name, "arguments": arguments or {}})
        if not isinstance(result, dict):
            return result
        content = result.get("content", [])
        if len(content) == 1 and isinstance(content[0], dict):
            item = content[0]
            if "json" in item:
                return item["json"]
            if item.get("type") == "text":
                return item.get("text")
        return result

    def call_if_available(self, name: str, arguments: dict[str, Any] | None = None) -> Any | None:
        try:
            if self.has_tool(name):
                return self.call_tool(name, arguments)
        except Exception:
            return None
        return None
