"""CentralMemory singleton initialization for PyRIT."""

from __future__ import annotations

_initialized = False


def ensure_memory() -> None:
    """Initialize PyRIT CentralMemory with in-memory SQLite (idempotent)."""
    global _initialized
    if _initialized:
        return

    from pyrit.memory import CentralMemory, SQLiteMemory

    mem = SQLiteMemory(db_path=":memory:", silent=True)
    CentralMemory.set_memory_instance(mem)
    _initialized = True
