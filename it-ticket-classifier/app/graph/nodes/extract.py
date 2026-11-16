import asyncio
import logging
from pathlib import Path

from app.core.config import get_settings
from app.core.security import sanitize_for_llm
from app.graph.state import AgentState, ExtractedChunk
from app.llm.client import LLMUsageTracker, OpenAIClassificationClient
from app.parsers.registry import category_for_filename, select_parser

logger = logging.getLogger(__name__)
settings = get_settings()


async def _read_attachment(path: str) -> bytes:
    return await asyncio.to_thread(Path(path).read_bytes)


async def _process_attachment_list(
    state: AgentState,
    *,
    branch: str,
    categories: set[str],
    extensions: set[str] | None = None,
) -> dict:
    llm = OpenAIClassificationClient(settings)
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
    return partial


async def _parse_one(att: dict, llm: OpenAIClassificationClient, usage: LLMUsageTracker, branch: str):
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


async def process_text(state: AgentState) -> dict:
    desc = (state.get("description") or "").strip()
    if not desc:
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
    return {"extracted_content": [chunk]}


async def process_documents(state: AgentState) -> dict:
    return await _process_attachment_list(
        state,
        branch="docs",
        categories={"document", "presentation", "spreadsheet", "text", "structured"},
        extensions=None,
    )


async def process_images(state: AgentState) -> dict:
    return await _process_attachment_list(
        state,
        branch="images",
        categories={"image"},
        extensions={"png", "jpg", "jpeg", "webp"},
    )


async def process_diagrams(state: AgentState) -> dict:
    return await _process_attachment_list(
        state,
        branch="diagrams",
        categories={"diagram"},
        extensions={"vsdx", "vsd"},
    )