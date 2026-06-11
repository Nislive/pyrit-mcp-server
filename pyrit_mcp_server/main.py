"""
PyRIT Red Teaming MCP Server — entry point.

A modular FastMCP server exposing Microsoft PyRIT (0.14.0) as ~30 MCP tools
for authorized AI security testing.

Usage:
    python -m pyrit_mcp_server.main
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("PyRIT Red Teaming Server")

# Register all tool modules on the single FastMCP instance
from pyrit_mcp_server.tools import (
    attacks,
    converters,
    datasets,
    memory_tools,
    scenarios,
    scoring,
    targets,
)

targets.register(mcp)
attacks.register(mcp)
scoring.register(mcp)
converters.register(mcp)
scenarios.register(mcp)
datasets.register(mcp)
memory_tools.register(mcp)


if __name__ == "__main__":
    mcp.run()
