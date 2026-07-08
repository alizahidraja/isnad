"""ISNAD CLI — entry point for serve, seed, and eval commands.

Usage:
    isnad serve          Start the API server
    isnad seed --config  Seed narrators from JSON config
"""

from __future__ import annotations

import json
import os
import sys


def serve() -> None:
    """Start the ISNAD API server."""
    import uvicorn

    host = os.environ.get("ISNAD_HOST", "0.0.0.0")
    port = int(os.environ.get("ISNAD_PORT", "8000"))
    uvicorn.run("isnad.api.app:app", host=host, port=port, reload=False)


def seed() -> None:
    """Seed the narrator registry from ISNAD_SEED_CONFIG env var."""
    from isnad.storage.sqlalchemy import get_session, init_db

    init_db()
    config = json.loads(os.environ.get("ISNAD_SEED_CONFIG", "[]"))
    if not config:
        print("ISNAD_SEED_CONFIG is empty. Set it to a JSON array of {narrator_id, domain, grade}.")
        sys.exit(1)

    from isnad.core.registry import NarratorGrade, RegistryDB

    grade_map = {
        "reliable": NarratorGrade.RELIABLE,
        "acceptable": NarratorGrade.ACCEPTABLE,
        "weak": NarratorGrade.WEAK,
        "rejected": NarratorGrade.REJECTED,
        "ungraded": NarratorGrade.UNGRADED,
    }

    with get_session() as session:
        reg = RegistryDB(session=session)
        reg.load()
        for entry in config:
            nid = entry["narrator_id"]
            dom = entry.get("domain", "general")
            grade = grade_map.get(entry.get("grade", "ungraded"), NarratorGrade.UNGRADED)
            reg.registry.register(nid, dom, grade=grade)
        reg.flush()
        print(f"Seeded {len(config)} narrators.")


def main() -> None:
    """CLI dispatcher."""
    if len(sys.argv) < 2:
        print("Usage: isnad [serve|seed]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "serve":
        serve()
    elif cmd == "seed":
        seed()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: isnad [serve|seed]")
        sys.exit(1)


if __name__ == "__main__":
    main()
