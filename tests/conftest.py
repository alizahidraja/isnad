"""Test environment setup.

Sets ISNAD_API_KEYS explicitly so API tests exercise the fail-closed auth path
against a known key set, rather than relying on the now-removed hardcoded
default credential (issue #93).
"""

from __future__ import annotations

import os

os.environ.setdefault("ISNAD_API_KEYS", "isnad-admin:admin,isnad-reader:reader")
