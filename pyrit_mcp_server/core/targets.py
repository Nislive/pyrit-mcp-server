"""Runtime target registry — create, retrieve and remove PromptTarget instances."""

from __future__ import annotations

import uuid
from typing import Any


class TargetRegistry:
    """In-memory store of PromptTarget instances keyed by target_id."""

    _targets: dict[str, Any] = {}

    @classmethod
    def create_openai(
        cls,
        *,
        endpoint: str,
        model_name: str,
        api_key: str | None = None,
        target_id: str | None = None,
    ) -> str:
        """Create an OpenAIChatTarget and store it. Returns target_id."""
        from pyrit.prompt_target import OpenAIChatTarget

        tid = target_id or str(uuid.uuid4())[:8]
        cls._targets[tid] = OpenAIChatTarget(
            endpoint=endpoint,
            model_name=model_name,
            api_key=api_key or None,
        )
        return tid

    @classmethod
    def get(cls, target_id: str) -> Any:
        """Return a target by id. Raises KeyError if not found."""
        if target_id not in cls._targets:
            raise KeyError(
                f"Target '{target_id}' not found. "
                f"Available: {list(cls._targets.keys())}. "
                f"Use create_target tool first."
            )
        return cls._targets[target_id]

    @classmethod
    def remove(cls, target_id: str) -> bool:
        """Remove a target. Returns True if it existed."""
        return cls._targets.pop(target_id, None) is not None

    @classmethod
    def list_all(cls) -> dict[str, str]:
        """Return {target_id: class_name} for all registered targets."""
        return {tid: type(t).__name__ for tid, t in cls._targets.items()}

    @classmethod
    def _new_instance(cls, target_id: str) -> Any:
        """Create a fresh instance with the same config (for scorer/adversarial isolation)."""
        original = cls.get(target_id)
        from pyrit.prompt_target import OpenAIChatTarget

        if isinstance(original, OpenAIChatTarget):
            return OpenAIChatTarget(
                endpoint=original._endpoint,
                model_name=original._model_name,
                api_key=original._api_key,
            )
        return original
