"""CrewAI adapter — capture a crew/agent run as an isnād (issue #70).

CrewAI is **not** LangChain-based, so this is a separate collector. Agents are
the transmitters; the ordered sequence of agents that ran a crew is the isnād.

Honest limit: the collector records *who* ran, in order, and grades that chain
from the registry. It duck-types CrewAI's callback objects (no ``crewai``
import, so it is safe to ship without the framework). **Live verification needs
``crewai`` installed + an LLM**; the collector's core logic is unit-tested.
"""

from __future__ import annotations

from isnad.core.grading import grade_chain
from isnad.core.registry import Registry
from isnad.types import TransformType


class CrewLineageCollector:
    """Record the ordered agent lineage of a CrewAI run and grade it.

    Attach ``step_callback``/``task_callback`` to CrewAI agents/tasks, then call
    ``grade()``. Agents map to narrators ``agent:<role>``.
    """

    def __init__(
        self,
        registry: Registry,
        domain: str = "general",
        *,
        lenient_unknown: bool = False,
    ) -> None:
        self.registry = registry
        self.domain = domain
        self.lenient_unknown = lenient_unknown
        self._agents: list[str] = []

    def record_agent(self, role: str) -> None:
        """Record one transmitter by role (e.g. ``"researcher"``)."""
        self._agents.append(role)

    def step_callback(self, step: object) -> None:
        """CrewAI ``step_callback`` hook — best-effort role extraction."""
        role = getattr(step, "role", None) or getattr(step, "agent_role", None)
        if role:
            self.record_agent(str(role))

    def task_callback(self, task: object) -> None:
        """CrewAI ``Task.callback`` hook — receives a ``TaskOutput`` whose
        ``.agent`` is the role string (e.g. ``"researcher"``)."""
        agent = getattr(task, "agent", None)
        if isinstance(agent, str):
            self.record_agent(agent)
            return
        role = getattr(task, "agent_role", None)
        if role is None and agent is not None:
            role = getattr(agent, "role", None)
        if role:
            self.record_agent(str(role))

    def grade(self) -> dict[str, object]:
        """Grade the collected lineage, weakest-link, from the registry."""
        narrators = [f"agent:{role}" for role in self._agents]
        grades = [self.registry.get_grade(nid, self.domain) for nid in narrators]
        chain_grade = grade_chain(
            grades,
            [TransformType.PASS_THROUGH] * len(grades),
            is_complete=True,
            lenient_unknown=self.lenient_unknown,
        )
        return {
            "agents": narrators,
            "grades": [g.value for g in grades],
            "chain_grade": chain_grade.value,
        }
