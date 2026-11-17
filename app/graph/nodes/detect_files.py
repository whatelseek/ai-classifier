"""LangGraph node: decide which parallel extraction branches to run."""

import logging
import time

from app.graph.state import AgentState
from app.graph.telemetry import log_node
from app.parsers.registry import category_for_filename, parser_kind_for_file

logger = logging.getLogger(__name__)


def detect_attachments(state: AgentState) -> dict:
    """Set branch flags for text, documents, images, and diagrams.

    Args:
        state: Graph state after validation.

    Returns:
        Partial update with a ``branches`` dictionary for logs. Fan-out itself
        sends one worker per attachment.
    """
    started = time.perf_counter()
    attachments = state.get("attachments") or []
    branches = {
        "text": bool((state.get("description") or "").strip()),
        "docs": False,
        "images": False,
        "diagrams": False,
    }

    for att in attachments:
        cat = category_for_filename(att["filename"])
        kind = parser_kind_for_file(att["filename"])
        if cat in ("document", "presentation", "spreadsheet") and cat != "image":
            if att["filename"].lower().endswith(".csv") or cat == "spreadsheet":
                branches["docs"] = True
            else:
                branches["docs"] = True
        elif cat == "image":
            branches["images"] = True
        elif cat == "diagram":
            branches["diagrams"] = True
        elif cat in ("text", "structured") or kind is not None:
            branches["docs"] = True

    log_node(logger, "detect_attachments", started, **{f"branch_{k}": v for k, v in branches.items()})
    return {"branches": branches}