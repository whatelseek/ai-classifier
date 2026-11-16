"""LangGraph nodes: parallel text, document, image, and diagram extraction."""

import asyncio
import logging
import time
from pathlib import Path

from langgraph.errors import NodeError
from langgraph.runtime import Runtime

from app.core.errors import EXTRACTION_FAILED
from app.core.security import sanitize_for_llm
from app.graph.context import GraphContext, llm_from_runtime
from app.graph.state import AgentState, ExtractedChunk
from app.graph.telemetry import log_node
from app.llm.client import LLMUsageTracker, OpenAIClassificationClient
from app.parsers.registry import category_for_filename, select_parser

logger = logging.getLogger(__name__)


async def _read_attachment(path: str) -> bytes:
    """Load attachment bytes from a temp path without blocking the event loop."""
    return await asyncio.to_thread(Path(path).read_bytes)


async def _process_attachment_list(
    state: AgentState,
    runtime: Runtime[GraphContext],
    *,
    branch: str,
    categories: set[str],
    extensions: set[str] | None = None,
) -> dict:
    """Parse attachments matching category or extension filters.

    Fan-out sends one attachment per invocation. Several invocations of the
    same node still run concurrently, bounded by ``max_concurrency``.

    Args:
        state: Graph state with attachment metadata.
        runtime: Runtime context carrying the shared LLM client.
        branch: Branch name recorded on each extracted chunk.
        categories: Allowed ``EXTENSION_TO_CATEGORY`` values.
        extensions: When set, restrict to these file extensions.

    Returns:
        Partial state with ``extracted_content`` and ``attachment_statuses``.
    """
    started = time.perf_counter()
    llm = llm_from_runtime(runtime)
    usage = LLMUsageTracker()
    tasks: list = []
    metas: list[tuple[str, str]] = []

    for att in state.get("attachments") or []:
        cat = category_for_filename(att["filename"]) or ""
        ext = Path(att["filename"]).suffix.lstrip(".").lower()
        if extensions is not None and ext not in extensions:
            continue
        if extensions is None and (cat not in categories or cat in ("image", "diagram")):
            continue
        tasks.append(_parse_one(att, llm, usage, branch))
        metas.append((att["filename"], branch))

    results = await asyncio.gather(*tasks) if tasks else []

    extracted: list[ExtractedChunk] = []
    statuses: list[dict] = []
    for result in results:
        chunk: ExtractedChunk = {
            "filename": result.filename,
            "parser": result.parser,
            "status": result.status,
            "text": result.text,
            "source_ref": result.source_ref or result.filename,
            "branch": branch,
        }
        extracted.append(chunk)
        statuses.append(
            {
                "filename": result.filename,
                "status": "processed" if result.status == "processed" else "failed",
                "parser": result.parser,
                "error": result.error,
            }
        )

    partial: dict = {
        "extracted_content": extracted,
        "attachment_statuses": statuses,
    }
    if usage.llm_calls:
        partial["llm_calls"] = usage.llm_calls
        partial["token_usage"] = usage.token_usage
    log_node(
        logger,
        branch,
        started,
        files=len(statuses),
        failed=sum(1 for item in statuses if item["status"] != "processed"),
        llm_calls=usage.llm_calls,
    )
    return partial


async def _parse_one(att: dict, llm: OpenAIClassificationClient, usage: LLMUsageTracker, branch: str):
    """Select a parser and run it for one attachment metadata row."""
    parser = select_parser(att["filename"], llm, usage)
    if not parser:
        from app.parsers.base import ParseResult

        return ParseResult(
            filename=att["filename"],
            parser="none",
            status="failed",
            error="No parser available for file type",
        )
    data = await _read_attachment(att["path"])
    return await parser.parse(att["filename"], data, att.get("content_type"))


def extraction_error_handler(state: AgentState, error: NodeError) -> dict:
    """Convert an extraction-node failure into a per-file status.

    Args:
        state: Worker state. Fan-out puts a single attachment here.
        error: Node failure context. The exception text is logged, not returned.

    Returns:
        Partial update with a failed attachment status.
    """
    logger.error("Extraction node %s failed", error.node, exc_info=error.error)
    attachments = state.get("attachments") or []
    filename = attachments[0]["filename"] if attachments else error.node
    return {
        "attachment_statuses": [
            {
                "filename": filename,
                "status": "failed",
                "parser": error.node,
                "error": EXTRACTION_FAILED,
            }
        ],
        "extracted_content": [
            {
                "filename": filename,
                "parser": error.node,
                "status": "failed",
                "text": "",
                "source_ref": filename,
                "branch": error.node,
            }
        ],
    }


async def process_text(state: AgentState) -> dict:
    """Add the ticket description as an extracted text chunk."""
    started = time.perf_counter()
    desc = (state.get("description") or "").strip()
    if not desc:
        log_node(logger, "process_text", started, files=0)
        return {}
    text = sanitize_for_llm(desc)
    chunk: ExtractedChunk = {
        "filename": "(description)",
        "parser": "text",
        "status": "processed",
        "text": text,
        "source_ref": "description",
        "branch": "text",
    }
    log_node(logger, "process_text", started, files=1)
    return {"extracted_content": [chunk]}


async def process_documents(state: AgentState, runtime: Runtime[GraphContext]) -> dict:
    """Extract office documents, spreadsheets, and plain structured text files."""
    return await _process_attachment_list(
        state,
        runtime,
        branch="docs",
        categories={"document", "presentation", "spreadsheet", "text", "structured"},
        extensions=None,
    )


async def process_images(state: AgentState, runtime: Runtime[GraphContext]) -> dict:
    """Extract technical context from raster screenshots via vision models."""
    return await _process_attachment_list(
        state,
        runtime,
        branch="images",
        categories={"image"},
        extensions={"png", "jpg", "jpeg", "webp"},
    )


async def process_diagrams(state: AgentState, runtime: Runtime[GraphContext]) -> dict:
    """Extract Visio diagram elements and relationships."""
    return await _process_attachment_list(
        state,
        runtime,
        branch="diagrams",
        categories={"diagram"},
        extensions={"vsdx", "vsd"},
    )