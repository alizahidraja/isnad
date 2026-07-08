"""Registry persistence protocol — pluggable storage backend.

The in-memory Registry is the pure-logic core.
RegistryDB (in storage/sqlalchemy.py) is one implementation.
Swap in Redis, DynamoDB, etc. by implementing this protocol.
"""

from __future__ import annotations

from typing import Protocol

from isnad.types import NarratorGrade


class RegistryPersistence(Protocol):
    """Protocol for persisting the narrator registry.

    This is one instantiation of a parameter the framework leaves open.
    Swap freely.
    """

    def load(self) -> None:
        """Load all narrators from persistent storage into the registry."""
        ...

    def flush(self) -> None:
        """Persist all in-memory narrators to storage."""
        ...

    def get_grade(self, narrator_id: str, domain_tag: str) -> NarratorGrade:
        """Return a narrator's grade, defaulting to UNGRADED if unknown."""
        ...

    def get_metadata(self, narrator_id: str, domain_tag: str) -> dict[str, object]:
        """Return narrator metadata for correlation detection."""
        ...
