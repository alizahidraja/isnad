"""Cold-start bootstrapping: Registry.seed / seed_from_benchmark (issue #33).

A bare ``register(grade=...)`` is silently clobbered to WEAK by the Bayesian
policy on the first piece of evidence. ``Registry.seed`` records the seed as
``BOOTSTRAP_SEED`` evidence so it (a) survives the posterior's first recompute
(issue #90) and (b) is visible in the evidence log as a prior (issue #6).
"""

from __future__ import annotations

from isnad.core.registry import Registry, accuracy_to_grade, seed_from_benchmark
from isnad.integrations.langchain import seed_registry
from isnad.types import EvidenceAction, EvidenceType, NarratorGrade, Role


class TestRegistrySeed:
    def test_seed_sets_grade_and_records_evidence(self) -> None:
        reg = Registry()
        reg.seed("model:x@v1", "physics", NarratorGrade.RELIABLE, source="benchmark")
        n = reg.get("model:x@v1", "physics")
        assert n is not None
        assert n.grade == NarratorGrade.RELIABLE
        # The seed is recorded as BOOTSTRAP_SEED evidence, not a silent grade.
        assert any(e["evidence_type"] == EvidenceType.BOOTSTRAP_SEED.value for e in n.evidence_log)

    def test_seed_survives_subsequent_evidence(self) -> None:
        """The whole point of #33 + #90: a seed must not collapse on first evidence."""
        reg = Registry()
        reg.seed("model:x@v1", "physics", NarratorGrade.RELIABLE)
        reg.record_evidence(
            "model:x@v1",
            "physics",
            EvidenceType.POST_HOC_AUDIT,
            EvidenceAction.TADIL,
            "one good audit",
        )
        assert reg.get_grade("model:x@v1", "physics") == NarratorGrade.RELIABLE

    def test_seed_reports_prior_provenance(self) -> None:
        reg = Registry()
        reg.seed("model:x@v1", "physics", NarratorGrade.ACCEPTABLE)
        summary = reg.evidence_provenance("model:x@v1", "physics")
        assert summary.prior_count >= 1
        assert summary.prior_only is True  # a seed is an assumption, not an observation

    def test_seed_role_scoped(self) -> None:
        """Per-role seeding (issue #3): precision is per (narrator, role, domain)."""
        reg = Registry()
        reg.seed("model:x@v1", "physics", NarratorGrade.RELIABLE, role=Role.SYNTHESIS)
        assert reg.get_grade("model:x@v1", "physics", role=Role.SYNTHESIS) == NarratorGrade.RELIABLE


class TestAccuracyToGrade:
    def test_thresholds(self) -> None:
        assert accuracy_to_grade(0.95) == NarratorGrade.RELIABLE
        assert accuracy_to_grade(0.90) == NarratorGrade.RELIABLE
        assert accuracy_to_grade(0.85) == NarratorGrade.ACCEPTABLE
        assert accuracy_to_grade(0.75) == NarratorGrade.ACCEPTABLE
        assert accuracy_to_grade(0.70) == NarratorGrade.WEAK
        assert accuracy_to_grade(0.60) == NarratorGrade.WEAK
        assert accuracy_to_grade(0.50) == NarratorGrade.REJECTED


class TestSeedFromBenchmark:
    def test_maps_accuracy_and_records_metadata(self) -> None:
        reg = Registry()
        grade = seed_from_benchmark(reg, "model:y@v2", "physics", 0.93, benchmark="mmlu")
        assert grade == NarratorGrade.RELIABLE
        n = reg.get("model:y@v2", "physics")
        seed_entry = next(
            e for e in n.evidence_log if e["evidence_type"] == EvidenceType.BOOTSTRAP_SEED.value
        )
        assert seed_entry["metadata"]["seed_source"] == "benchmark:mmlu"
        assert seed_entry["metadata"]["benchmark_accuracy"] == 0.93


class TestSeedRegistryHelper:
    def test_helper_produces_evidence_backed_seed(self) -> None:
        reg = seed_registry({"model:gpt-4o@v1": "reliable"}, domain="physics")
        assert reg.get_grade("model:gpt-4o@v1", "physics") == NarratorGrade.RELIABLE
        # Survives the first evidence (the #33 fix: the helper now uses seed()).
        reg.record_evidence(
            "model:gpt-4o@v1", "physics", EvidenceType.POST_HOC_AUDIT, EvidenceAction.TADIL, "ok"
        )
        assert reg.get_grade("model:gpt-4o@v1", "physics") == NarratorGrade.RELIABLE
