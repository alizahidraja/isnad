"""Tests for ISNAD content critics."""

from isnad.critics.embedding import EmbeddingCritic
from isnad.types import ContentVerdict


class TestEmbeddingCritic:
    def test_never_consistent_on_exact_match(self) -> None:
        """D2: TF-IDF never affirms consistency — an exact lexical match is
        still UNVERIFIABLE (overlap is conformity, not evidence)."""
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "force equals mass times acceleration",
            "force equals mass times acceleration",
            ["force equals mass times acceleration"],
        )
        assert result == ContentVerdict.UNVERIFIABLE

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

        assert result == ContentVerdict.UNVERIFIABLE

    def test_numeric_divergence_contradiction(self) -> None:
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "the value is 100 meters per second",
            "the value is 100 meters per second",
            ["the value is 10 meters per second"],
        )
        # 10x difference → potential contradiction
        assert result == ContentVerdict.CONTRADICTION

    def test_small_numeric_divergence_is_not_blessed(self) -> None:
        """D2: a <=3x dose error must NOT be blessed as CONSISTENT."""
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "the dose is 20 milligrams",
            "the dose is 20 milligrams",
            ["the dose is 10 milligrams"],
        )
        # 2x divergence — below the >3x gate — so it is NOT a contradiction,
        # but TF-IDF must still never affirm it as CONSISTENT.
        assert result == ContentVerdict.UNVERIFIABLE

    def test_zero_vs_nonzero_numeric_divergence(self) -> None:
        """Zero vs a non-zero magnitude is a real contradiction (was skipped)."""
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "water freezes at one hundred degrees celsius",
            "water freezes at one hundred degrees celsius",
            ["water freezes at zero degrees celsius"],
        )
        assert result == ContentVerdict.CONTRADICTION

    def test_word_number_divergence_infinite(self) -> None:
        """'infinite' vs a finite written-out magnitude is a contradiction."""
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "the speed of light in a vacuum is infinite",
            "the speed of light in a vacuum is infinite",
            ["the speed of light in a vacuum is about three hundred million meters per second"],
        )
        assert result == ContentVerdict.CONTRADICTION

    def test_directly_vs_inversely_proportional(self) -> None:
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "the wavelength of light is directly proportional to its frequency",
            "the wavelength of light is directly proportional to its frequency",
            ["the wavelength of light is inversely proportional to its frequency"],
        )
        assert result == ContentVerdict.CONTRADICTION

    def test_bare_proportional_vs_inversely(self) -> None:
        """A bare 'proportional' is the default (direct), so 'inversely' contradicts it."""
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "the energy of a photon is inversely proportional to its frequency",
            "the energy of a photon is inversely proportional to its frequency",
            ["the energy of a photon is proportional to its frequency"],
        )
        assert result == ContentVerdict.CONTRADICTION

    def test_always_vs_never(self) -> None:
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "the entropy of an isolated system always decreases",
            "the entropy of an isolated system always decreases",
            ["the entropy of an isolated system never decreases"],
        )
        assert result == ContentVerdict.CONTRADICTION

    def test_created_vs_conserved(self) -> None:
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "energy can be created from nothing in an isolated system",
            "energy can be created from nothing in an isolated system",
            ["energy is conserved in an isolated system"],
        )
        assert result == ContentVerdict.CONTRADICTION

    def test_consistent_paraphrase_not_flagged(self) -> None:
        """A correct paraphrase must stay unflagged (no false-contradiction)."""
        critic = EmbeddingCritic()
        result = critic.evaluate(
            "in an isolated system the total energy does not change",
            "in an isolated system the total energy does not change",
            ["energy is conserved in an isolated system"],
        )
        assert result != ContentVerdict.CONTRADICTION
