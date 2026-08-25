"""LangGraph adapter — thin, because LangGraph already propagates LangChain callbacks.

LangGraph compiles a state graph whose nodes emit the same ``on_chain_*`` /
``on_llm_*`` events the LangChain ``IsnadCallbackHandler`` listens for. So the
existing callback captures LangGraph runs with no new machinery:

    from isnad.integrations.langgraph import IsnadCallbackHandler
    from isnad.integrations.langchain import seed_registry

    handler = IsnadCallbackHandler(registry=seed_registry({...}), domain="...")
    graph.invoke(state, config={"callbacks": [handler]})
    trace = handler.to_trace()
"""

from __future__ import annotations

from isnad.integrations.langchain.callback import IsnadCallbackHandler

__all__ = ["IsnadCallbackHandler"]
