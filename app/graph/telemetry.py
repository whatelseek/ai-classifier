"""Structured timing logs for LangGraph nodes."""

import logging
import time
from typing import Any

from app.core.logging import log_extra


def log_node(logger: logging.Logger, node: str, started: float, **fields: Any) -> None:
    """Log node completion with duration and structured fields.

    Args:
        logger: Logger for the node module.
        node: Graph node name.
        started: ``time.perf_counter`` value captured at node start.
        **fields: Extra JSON fields. Callers must omit ticket text and secrets.
    """
    log_extra(
        logger,
        logging.INFO,
        "graph node completed",
        node=node,
        duration_ms=int((time.perf_counter() - started) * 1000),
        **fields,
    )
