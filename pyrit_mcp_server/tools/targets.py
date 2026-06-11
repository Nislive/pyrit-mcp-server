"""MCP tools for managing PyRIT prompt targets."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from pyrit_mcp_server.core import TargetRegistry, ensure_memory


def register(mcp: FastMCP) -> None:
    """Register target-management tools on the MCP server."""

    @mcp.tool()
    async def create_target(
        endpoint: str,
        model_name: str,
        api_key: str = "",
        target_id: str = "",
    ) -> dict[str, Any]:
        """Create an OpenAI-compatible chat target.

        Args:
            endpoint: API endpoint URL (e.g. https://api.openai.com/v1).
            model_name: Model or deployment name (e.g. gpt-4o).
            api_key: API key. Leave empty for Azure Entra ID auth.
            target_id: Optional custom ID. Auto-generated if empty.

        Returns:
            Dict with target_id.
        """
        try:
            ensure_memory()
            tid = TargetRegistry.create_openai(
                endpoint=endpoint,
                model_name=model_name,
                api_key=api_key or None,
                target_id=target_id or None,
            )
            return {"status": "success", "target_id": tid}
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    @mcp.tool()
    async def list_targets() -> dict[str, Any]:
        """List all registered targets.

        Returns:
            Dict mapping target_id to target class name.
        """
        return {"status": "success", "targets": TargetRegistry.list_all()}

    @mcp.tool()
    async def remove_target(target_id: str) -> dict[str, Any]:
        """Remove a registered target by ID.

        Args:
            target_id: The target to remove.

        Returns:
            Dict with removal status.
        """
        removed = TargetRegistry.remove(target_id)
        return {"status": "success", "removed": removed}
