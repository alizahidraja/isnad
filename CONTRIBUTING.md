# Contributing to Isnād

The Isnād–Rijāl framework is designed to be a collaborative research codebase — modular, well-typed, and tested. Contributions are welcome.

## Getting started

```bash
git clone https://github.com/alizahidraja/isnad.git
cd isnad
make install
make test
```

## Development workflow

- **uv** manages dependencies: `uv sync --all-extras`
- **ruff** formats/lints: `make lint` (or `make lint-fix` to auto-fix)
- **mypy** type-checks in strict mode: `make typecheck`
- **pytest** runs the suite: `make test`
- **All three at once:** `make check`

CI enforces all three on push/PR.

## Code conventions

- Full type hints everywhere. No `Any` without justification.
- Docstrings on all public functions and classes.
- The paper's epistemic commitments are non-negotiable — see each module's docstring.
- Pluggable strategies must implement their Protocol and note in their docstring: *"This is one instantiation of a parameter the framework leaves open (see paper §4.2/§4.3). Swap freely."*
- Reference stubs must be labeled as such in docstrings with a note on what production needs.

## How to add a new strategy (the most common contribution)

The framework has five pluggable strategy interfaces (see `isnad/types.py`). Here's the pattern:

1. Create a class implementing the Protocol.
2. Pass it to the relevant function instead of the default.

```python
from isnad.types import GradingStrategy, NarratorGrade, TransformType, ChainGrade

class MyGradingStrategy:
    """Custom chain-grading heuristic. Swap freely."""
    def compute_chain_grade(
        self,
        link_narrator_grades: list[NarratorGrade],
        link_transform_types: list[TransformType],
        is_complete: bool,
        *,
        corroboration_support: bool = False,
    ) -> ChainGrade:
        # Your logic
        ...

# Use it
from isnad import grade_chain
result = grade_chain(grades, transforms, is_complete=True, strategy=MyGradingStrategy())
```

Same pattern applies to `TransitionPolicy`, `CorroborationPolicy`, `CorrelationDetector`, and `ContentCritic`.

## Good first issues

1. **Alternative `CorrelationDetector` using embedding similarity** — compare model output embeddings to detect correlated blind spots, not just shared model family names. Replace or extend `SharedLineageDetector`.

2. **Seed-grade bootstrapper** — implement a `bootstrap_registry()` that initializes narrator grades from published benchmark accuracies (MMLU, HumanEval, etc.) and source reputation data. See paper §7 ("Registry cold start").

3. **Domain-specific `ContentCritic`** — add a physics critic that normalizes formulas (unit-canonicalization, symbol resolution) before comparing, or a medical critic with UMLS-based concept normalization.

4. **Calibrated `TransitionPolicy`** — if you have pipeline data from a real deployment, contribute your calibrated thresholds (downgrade/upgrade counts) as an alternative `TransitionPolicy`.

5. **Pipeline adapter** — write a connector that maps LangChain/CrewAI/Autogen traces into the `ChainLinkSpec` format, populating `trace_id`, `version`, and `transform_type` automatically.

## Tests

- Every epistemic commitment from the paper must have at least one explicit test.
- New strategy implementations must include tests demonstrating protocol conformance.
- The worked example test (`tests/test_worked_example.py`) is the integration anchor — keep it passing.
- Run `make coverage` to check coverage.

## Code of Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
