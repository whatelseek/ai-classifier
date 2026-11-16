"""Runtime context passed into LangGraph nodes.

The OpenAI client lives here instead of in graph state so nodes can share one
connection pool and tests can inject a fake client.
"""

from typing import TypedDict

from langgraph.runtime import Runtime

from app.core.config import get_settings
from app.llm.client import OpenAIClassificationClient


class GraphContext(TypedDict, total=False):
    """Dependencies available to every node for a single invocation.

    Attributes:
        llm_client: Shared Responses API client. When omitted, nodes build one
            from process settings.
    """

    llm_client: OpenAIClassificationClient


def llm_from_runtime(runtime: Runtime[GraphContext] | None) -> OpenAIClassificationClient:
    """Return the request-scoped LLM client, or a settings-backed fallback.

    Args:
        runtime: LangGraph runtime injected into the node. May be missing in
            direct unit calls.

    Returns:
        Client used for classification and vision.
    """
    context = getattr(runtime, "context", None) if runtime is not None else None
    client: OpenAIClassificationClient | None = None
    if isinstance(context, dict):
        client = context.get("llm_client")
    elif context is not None:
        client = getattr(context, "llm_client", None)
    if client is not None:
        return client
    return OpenAIClassificationClient(get_settings())
