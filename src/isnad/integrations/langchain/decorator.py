"""@isnad_track decorator — simple ISNAD provenance for functions.

For developers not using the full LangChain callback machinery.
Wraps a function that produces a claim and records its transmission
chain into a registry.
"""

from __future__ import annotations

import functools
import uuid
from collections.abc import Callable
from typing import Any

from isnad.chain import Chain, ChainLinkSpec
from isnad.grading import grade_chain
from isnad.registry import Registry
from isnad.types import TransformType


def isnad_track(
    registry: Registry,
    narrator_id: str = "function",
    domain: str = "general",
    transform_type: TransformType = TransformType.GENERATIVE,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that records ISNAD provenance for a function's output.

    Args:
        registry: The ISNAD Registry to record narrators in.
        narrator_id: Identifier for this function as a narrator.
        domain: Domain tag for the narrator's claims.
        transform_type: TransformType for this function.

    Example:
        reg = Registry()
        reg.register("my-model", "general", grade=NarratorGrade.ACCEPTABLE)

        @isnad_track(registry=reg, narrator_id="my-model")
        def answer_question(query: str) -> str:
            return llm.invoke(query)

        result = answer_question("What is F=ma?")
        # Chain automatically recorded in registry
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)

            if isinstance(result, str):
                claims = [result]
            elif isinstance(result, list):
                claims = [str(r) for r in result]
            else:
                claims = [str(result)]

            for _claim_text in claims:
                chain = Chain(
                    [
                        ChainLinkSpec(
                            narrator_id=narrator_id,
                            step=0,
                            domain=domain,
                            transform_type=transform_type,
                            trace_id=str(uuid.uuid4())[:8],
                        )
                    ]
                )

                # Register narrator if not already present
                if (narrator_id, domain) not in registry:
                    registry.register(narrator_id, domain)

                link_grades = [
                    registry.get_grade(link.narrator_id, link.domain) for link in chain.links
                ]
                link_transforms = [link.transform_type for link in chain.links]

                wrapper._last_grade = grade_chain(  # type: ignore[attr-defined]
                    link_grades,
                    link_transforms,
                    is_complete=chain.is_complete,
                )
                wrapper._last_chain = chain  # type: ignore[attr-defined]

            return result

        wrapper._last_grade = None  # type: ignore[attr-defined]
        wrapper._last_chain = None  # type: ignore[attr-defined]
        return wrapper

    return decorator
