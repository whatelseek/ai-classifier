"""LangGraph StateGraph construction for the classification workflow."""

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.graph.edges import (
    fan_out_processing,
    mark_needs_review,
    route_after_confidence,
    route_after_validate,
)
from app.graph.nodes.classify import classify_function
from app.graph.nodes.detect_files import detect_attachments
from app.graph.nodes.evaluate import (
    evaluate_confidence,
    format_response,
    retry_classification,
    return_validation_error,
)
from app.graph.nodes.extract import (
    process_diagrams,
    process_documents,
    process_images,
    process_text,
)
from app.graph.nodes.merge import merge_context
from app.graph.nodes.validate import validate_request
from app.graph.state import AgentState


def build_classification_graph():
    """Wire nodes, conditional edges, and compile the LangGraph workflow.

    Returns:
        Compiled graph implementing validate → extract → classify → evaluate.
    """
    graph = StateGraph(AgentState)

    graph.add_node("validate_request", validate_request)
    graph.add_node("return_validation_error", return_validation_error)
    graph.add_node("detect_attachments", detect_attachments)
    graph.add_node("process_text", process_text)
    graph.add_node("process_documents", process_documents)
    graph.add_node("process_images", process_images)
    graph.add_node("process_diagrams", process_diagrams)
    graph.add_node("merge_context", merge_context)
    graph.add_node("classify_function", classify_function)
    graph.add_node("evaluate_confidence", evaluate_confidence)
    graph.add_node("retry_classification", retry_classification)
    graph.add_node("needs_review", mark_needs_review)
    graph.add_node("format_response", format_response)

    graph.add_edge(START, "validate_request")
    graph.add_conditional_edges(
        "validate_request",
        route_after_validate,
        {
            "detect_attachments": "detect_attachments",
            "return_validation_error": "return_validation_error",
        },
    )
    graph.add_edge("return_validation_error", END)

    graph.add_conditional_edges("detect_attachments", fan_out_processing)

    for node in ("process_text", "process_documents", "process_images", "process_diagrams"):
        graph.add_edge(node, "merge_context")

    graph.add_edge("merge_context", "classify_function")
    graph.add_edge("classify_function", "evaluate_confidence")

    graph.add_conditional_edges(
        "evaluate_confidence",
        route_after_confidence,
        {
            "format_response": "format_response",
            "retry_classification": "retry_classification",
            "needs_review_path": "needs_review",
        },
    )
    graph.add_edge("retry_classification", "classify_function")
    graph.add_edge("needs_review", "format_response")
    graph.add_edge("format_response", END)

    return graph.compile()


@lru_cache
def get_graph():
    """Return a cached compiled classification graph.

    Returns:
        Singleton compiled LangGraph application.
    """
    return build_classification_graph()