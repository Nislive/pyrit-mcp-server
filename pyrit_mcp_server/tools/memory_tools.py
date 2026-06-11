"""MCP tools for querying PyRIT attack history and memory."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from pyrit_mcp_server.core import ensure_memory


def register(mcp: FastMCP) -> None:
    """Register memory/history tools on the MCP server."""

    @mcp.tool()
    async def get_attack_history(
        outcome: str = "",
        objective: str = "",
        max_items: int = 20,
    ) -> dict[str, Any]:
        """Retrieve previous attack results from memory.

        Args:
            outcome: Filter by outcome (success, failure, error, undetermined). Empty = all.
            objective: Filter by objective substring. Empty = all.
            max_items: Maximum results to return (default 20).

        Returns:
            Dict with list of attack result summaries.
        """
        try:
            ensure_memory()
            from pyrit.memory import CentralMemory

            memory = CentralMemory.get_memory_instance()

            kwargs: dict[str, Any] = {}
            if outcome:
                kwargs["outcome"] = outcome
            if objective:
                kwargs["objective"] = objective

            results = memory.get_attack_results(**kwargs)

            out = []
            for r in results:
                out.append({
                    "attack_result_id": r.attack_result_id,
                    "conversation_id": r.conversation_id,
                    "objective": r.objective,
                    "outcome": r.outcome.value,
                    "executed_turns": r.executed_turns,
                    "execution_time_ms": r.execution_time_ms,
                    "last_response": r.last_response.converted_value if r.last_response else None,
                    "score": {
                        "value": r.last_score.score_value,
                        "rationale": r.last_score.score_rationale,
                    } if r.last_score else None,
                    "timestamp": str(r.timestamp),
                })
                if len(out) >= max_items:
                    break

            return {"status": "success", "count": len(out), "results": out}
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    @mcp.tool()
    async def get_conversation(
        conversation_id: str,
    ) -> dict[str, Any]:
        """Retrieve full conversation history by conversation ID.

        Args:
            conversation_id: The conversation ID to retrieve.

        Returns:
            Dict with ordered list of messages (role, content, sequence).
        """
        try:
            ensure_memory()
            from pyrit.memory import CentralMemory

            memory = CentralMemory.get_memory_instance()
            messages = memory.get_conversation(conversation_id=conversation_id)

            out = []
            for msg in messages:
                for piece in msg.message_pieces:
                    out.append({
                        "role": piece.role,
                        "content": piece.converted_value,
                        "data_type": piece.converted_value_data_type,
                        "sequence": piece.sequence,
                        "timestamp": str(piece.timestamp) if hasattr(piece, "timestamp") else None,
                    })

            return {"status": "success", "conversation_id": conversation_id, "message_count": len(out), "messages": out}
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    @mcp.tool()
    async def export_results(
        outcome: str = "",
        max_items: int = 100,
    ) -> dict[str, Any]:
        """Export attack results as structured data for reporting.

        Args:
            outcome: Filter by outcome. Empty = all.
            max_items: Maximum results (default 100).

        Returns:
            Dict with full attack result data suitable for JSON export.
        """
        try:
            ensure_memory()
            from pyrit.memory import CentralMemory

            memory = CentralMemory.get_memory_instance()

            kwargs: dict[str, Any] = {}
            if outcome:
                kwargs["outcome"] = outcome

            results = memory.get_attack_results(**kwargs)

            out = []
            for r in results:
                entry: dict[str, Any] = {
                    "attack_result_id": r.attack_result_id,
                    "conversation_id": r.conversation_id,
                    "objective": r.objective,
                    "outcome": r.outcome.value,
                    "outcome_reason": r.outcome_reason,
                    "executed_turns": r.executed_turns,
                    "execution_time_ms": r.execution_time_ms,
                    "error_message": r.error_message,
                    "error_type": r.error_type,
                    "labels": r.labels,
                    "timestamp": str(r.timestamp),
                }
                if r.last_response:
                    entry["last_response"] = {
                        "content": r.last_response.converted_value,
                        "data_type": r.last_response.converted_value_data_type,
                    }
                if r.last_score:
                    entry["last_score"] = {
                        "value": r.last_score.score_value,
                        "type": r.last_score.score_type,
                        "category": r.last_score.score_category,
                        "rationale": r.last_score.score_rationale,
                    }
                out.append(entry)
                if len(out) >= max_items:
                    break

            return {"status": "success", "count": len(out), "results": out}
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}
