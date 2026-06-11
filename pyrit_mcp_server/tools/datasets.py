"""MCP tools for PyRIT seed datasets."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from pyrit_mcp_server.core import ensure_memory


def register(mcp: FastMCP) -> None:
    """Register dataset tools on the MCP server."""

    @mcp.tool()
    async def list_seed_datasets() -> dict[str, Any]:
        """List available PyRIT seed datasets from the built-in dataset path.

        Returns:
            Dict with dataset file names found in PyRIT's datasets directory.
        """
        try:
            from pathlib import Path

            from pyrit.common.path import DATASETS_PATH

            datasets_path = Path(DATASETS_PATH)
            if not datasets_path.exists():
                return {"status": "success", "datasets": []}

            files = []
            for f in sorted(datasets_path.rglob("*.yaml")):
                files.append(str(f.relative_to(datasets_path)))
            for f in sorted(datasets_path.rglob("*.yml")):
                files.append(str(f.relative_to(datasets_path)))

            return {"status": "success", "count": len(files), "datasets": files}
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    @mcp.tool()
    async def load_objectives(
        dataset_name: str = "",
        harm_category: str = "",
        max_items: int = 20,
    ) -> dict[str, Any]:
        """Load seed objectives from PyRIT memory/datasets.

        Args:
            dataset_name: Filter by dataset name (substring match).
            harm_category: Filter by harm category (e.g. "violence", "hate_speech").
            max_items: Maximum number of items to return (default 20).

        Returns:
            Dict with list of seed objective values.
        """
        try:
            ensure_memory()
            from pyrit.memory import CentralMemory

            memory = CentralMemory.get_memory_instance()

            kwargs: dict[str, Any] = {}
            if dataset_name:
                kwargs["dataset_name_pattern"] = f"%{dataset_name}%"
            if harm_category:
                kwargs["harm_categories"] = [harm_category]

            seeds = memory.get_seeds(**kwargs)

            objectives = []
            for s in seeds:
                if hasattr(s, "value") and s.value:
                    objectives.append({
                        "value": s.value[:500],
                        "data_type": getattr(s, "data_type", None),
                        "harm_categories": getattr(s, "harm_categories", None),
                        "dataset_name": getattr(s, "dataset_name", None),
                    })
                    if len(objectives) >= max_items:
                        break

            return {"status": "success", "count": len(objectives), "objectives": objectives}
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}
