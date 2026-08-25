"""Real CrewAI test — an actual crew run with a DeepSeek LLM (marked ``llm``).

Runs a real CrewAI agent and verifies the lineage collector captures and grades
the run. Needs DEEPSEEK_API_KEY; excluded from CI by the ``llm`` marker.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("crewai")


@pytest.mark.llm
def test_crewai_real_run_captures_lineage():
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        pytest.skip("DEEPSEEK_API_KEY not set")

    from crewai import Agent, Crew, LLM, Task

    from isnad.core.registry import Registry
    from isnad.integrations.crewai import CrewLineageCollector
    from isnad.types import NarratorGrade

    reg = Registry()
    reg.register("agent:researcher", "general", grade=NarratorGrade.RELIABLE)
    collector = CrewLineageCollector(reg, domain="general")

    llm = LLM(model="deepseek-chat", base_url="https://api.deepseek.com/v1", api_key=key)
    agent = Agent(
        role="researcher",
        goal="Answer a trivial question in one word.",
        backstory="You are a minimal test agent.",
        llm=llm,
        verbose=False,
    )
    task = Task(
        description="Reply with exactly: hello",
        expected_output="hello",
        agent=agent,
        callback=collector.task_callback,
    )
    crew = Crew(agents=[agent], tasks=[task], verbose=False)
    crew.kickoff()

    grade = collector.grade()
    assert grade["agents"] == ["agent:researcher"]
    assert grade["chain_grade"] == "sahih"  # reliable researcher → sound chain
