"""Web search tool — DuckDuckGo (no-key), Brave, or Serper."""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from ag.tools.base import BaseTool, ToolResult


class WebSearchTool(BaseTool):
    """Search the web using DuckDuckGo (default), Brave, or Serper."""

    def __init__(self, config: dict) -> None:
        """Initialise WebSearchTool with config."""
        super().__init__("web_search", config)
        self.engine: str = config.get("engine", "duckduckgo")
        self.max_results: int = config.get("max_results", 5)
        self.brave_key: str = config.get("brave_api_key", "")
        self.serper_key: str = config.get("serper_api_key", "")

    async def run(self, query: str, **_: Any) -> ToolResult:
        """Search for *query* using the configured engine."""
        try:
            if self.engine == "brave" and self.brave_key:
                return await self._brave(query)
            if self.engine == "serper" and self.serper_key:
                return await self._serper(query)
            return await self._ddg(query)
        except Exception as exc:
            return ToolResult(tool=self.name, success=False, output="", error=str(exc))

    async def _ddg(self, query: str) -> ToolResult:
        """DuckDuckGo instant-answer & HTML search (no API key required)."""
        try:
            from duckduckgo_search import DDGS

            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=self.max_results):
                    results.append(f"**{r['title']}**\n{r['href']}\n{r['body']}\n")
            output = "\n---\n".join(results) if results else "No results found."
            return ToolResult(tool=self.name, success=True, output=output)
        except Exception as exc:
            return ToolResult(tool=self.name, success=False, output="", error=str(exc))

    async def _brave(self, query: str) -> ToolResult:
        """Brave Search API (requires BRAVE_API_KEY)."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": self.max_results},
                headers={"Accept": "application/json", "X-Subscription-Token": self.brave_key},
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("web", {}).get("results", [])
        lines = [f"**{r['title']}**\n{r['url']}\n{r.get('description','')}\n" for r in results]
        output = "\n---\n".join(lines) or "No results."
        return ToolResult(tool=self.name, success=True, output=output)

    async def _serper(self, query: str) -> ToolResult:
        """Serper.dev Google Search API (requires SERPER_API_KEY)."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                json={"q": query, "num": self.max_results},
                headers={"X-API-KEY": self.serper_key, "Content-Type": "application/json"},
                timeout=10,
            )
            resp.raise_for_status()
            organic = resp.json().get("organic", [])
        lines = [f"**{r['title']}**\n{r['link']}\n{r.get('snippet','')}\n" for r in organic]
        output = "\n---\n".join(lines) or "No results."
        return ToolResult(tool=self.name, success=True, output=output)

    def describe(self) -> dict:
        """Return OpenAI function schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web and return the top results as text.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query."},
                    },
                    "required": ["query"],
                },
            },
        }
