"""Tests for ISNAD content critics."""

from isnad.critics.embedding import EmbeddingCritic
from isnad.types import ContentVerdict


class TestEmbeddingCritic:
    def test_consistent_on_exact_match(self) -> None:
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "force equals mass times acceleration",
            "force equals mass times acceleration",
            ["force equals mass times acceleration"],
        )
        assert result == ContentVerdict.CONSISTENT

    def test_contradiction_on_negation(self) -> None:
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "energy is not conserved",
            "energy is not conserved",
            ["energy is conserved in all systems"],
        )
        assert result == ContentVerdict.CONTRADICTION

    def test_contradiction_on_opposite_words_with_high_overlap(self) -> None:
        """Word-overlap critic catches opposites when vocabulary overlaps."""
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "gravity is repulsive at large distances",
            "gravity is repulsive at large distances",
            ["gravity is attractive at all distances"],
        )
        # High word overlap (gravity, distances) + "repulsive" vs "attractive"
        assert result == ContentVerdict.CONTRADICTION

    def test_low_overlap_contradiction_missed(self) -> None:
        """Word-overlap critic MISSES contradictions with different vocabulary.
        This is a known limitation — the embedding critic uses surface-form
        word overlap, not semantic similarity."""
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "temperature decreases when heat is added",
            "temperature decreases when heat is added",
            ["temperature increases with added thermal energy"],
        )
        # Returns UNVERIFIABLE because word overlap is low
        # This is a real limitation documented in CRITIC_EVAL.md
        assert result == ContentVerdict.UNVERIFIABLE

    def test_unverifiable_on_empty_corpus(self) -> None:
        critic = EmbeddingCritic()
        result = critic.evaluate("anything", "anything", [])
        assert result == ContentVerdict.UNVERIFIABLE

    def test_unverifiable_on_unrelated_claims(self) -> None:
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "electrons have negative charge",
            "electrons have negative charge",
            ["apples grow on trees", "water is wet"],
        )
        assert result == ContentVerdict.UNVERIFIABLE

    def test_similar_but_not_contradictory(self) -> None:
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "momentum is mass times velocity",
            "momentum is mass times velocity",
            ["force equals mass times acceleration"],
        )
        # Similar (both about mass) but not contradictory
        assert result != ContentVerdict.CONTRADICTION

    def test_false_consistent_guard(self) -> None:
        """A claim using opposite vocabulary IS caught when word overlap is high."""
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "gravity is repulsive",
            "gravity is repulsive",
            ["gravity is attractive"],
        )
        # High overlap + opposite words → should catch
        assert result == ContentVerdict.CONTRADICTION, (
            f"False-CONSISTENT: critic returned {result.value}"
        )

    def test_custom_embed_fn(self) -> None:
        """EmbeddingCritic accepts no embed_fn — uses built-in TF-IDF.
        For custom embeddings, use HybridCritic."""
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "force equals mass times acceleration",
            "force equals mass times acceleration",
            ["force equals mass times acceleration"],
        )
        # TF-IDF with identical text → very high similarity → CONSISTENT
        assert result == ContentVerdict.CONSISTENT

    def test_numeric_divergence_contradiction(self) -> None:
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "the value is 100 meters per second",
            "the value is 100 meters per second",
            ["the value is 10 meters per second"],
        )
        # 10x difference → potential contradiction
        assert result == ContentVerdict.CONTRADICTION
