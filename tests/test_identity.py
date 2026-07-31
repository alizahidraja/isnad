"""Tests for narrator identity resolution (alias@version)."""

from isnad.core.identity import (
    NON_RESOLVED_VERSIONS,
    is_unknown_version,
    resolve_narrator_id,
)
from isnad.core.registry import Registry
from isnad.types import NarratorGrade


class TestNonResolvedVersions:
    def test_latest_dev_canary_are_non_resolved(self) -> None:
        for tag in ("latest", "dev", "canary", "LATEST", " Dev "):
            assert is_unknown_version(tag)

    def test_resolved_version_still_versioned(self) -> None:
        assert resolve_narrator_id("ingest-model-v3", "1.0") == "ingest-model-v3@1.0"

    def test_non_resolved_tags_use_alias_only(self) -> None:
        for tag in ("latest", "dev", "canary", "unknown"):
            assert resolve_narrator_id("ingest-model-v3", tag) == "ingest-model-v3"

    def test_register_versioned_latest_uses_alias_key(self) -> None:
        reg = Registry()
        reg.register_versioned("openstax-v3", "physics", "latest", grade=NarratorGrade.RELIABLE)

        assert reg.get("openstax-v3", "physics") is not None
        assert reg.get("openstax-v3@latest", "physics") is None
        assert reg.get_grade_for_link("openstax-v3", "physics", "latest") == NarratorGrade.RELIABLE

    def test_non_resolved_set_documents_placeholders(self) -> None:
        assert "latest" in NON_RESOLVED_VERSIONS
        assert "dev" in NON_RESOLVED_VERSIONS
        assert "canary" in NON_RESOLVED_VERSIONS
