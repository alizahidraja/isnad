"""Cross-process exclusive file-lock helper (flock on POSIX; no-op on Windows).

``exclusive_lock`` guards read-modify-append patterns so concurrent appenders do
not interleave or lose entries. The lock is held on a ``<path>.lock`` sidecar, so
it survives the lifetime of any single file descriptor.

Honest limits: the lock is POSIX-only (``fcntl.flock``). On Windows it is a
no-op, so multi-process chainlog/Merkle appends are single-writer there. On
network filesystems (NFS) ``flock`` is advisory and best-effort — do not rely on
it for cross-host mutual exclusion.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

try:
    import fcntl as _fcntl

    _HAS_FCNTL = True
except ImportError:  # pragma: no cover - Windows has no fcntl
    _fcntl = None  # type: ignore[assignment]
    _HAS_FCNTL = False


@contextlib.contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive advisory lock across a read-modify-append.

    POSIX: ``fcntl.flock(LOCK_EX)`` on the ``<path>.lock`` sidecar. Windows: a
    no-op fallback (best-effort; document the gap for multi-process writers).
    """
    if not _HAS_FCNTL:
        yield
        return
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = lock_path.open("a+")
    try:
        _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX)
        yield
    finally:
        try:
            _fcntl.flock(fh.fileno(), _fcntl.LOCK_UN)
        finally:
            fh.close()
