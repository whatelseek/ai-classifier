"""TypedDict definitions for LangGraph shared state and reducers."""

import operator
from typing import Annotated, Any, NotRequired, TypedDict


class AttachmentMeta(TypedDict):
    """Metadata for a persisted attachment on disk.

    Attributes:
        filename: Original upload name.
        content_type: MIME type if known.
        size: Size in bytes.
        category: High-level routing category (document, image, etc.).
        path: Absolute path to the temporary file.
    """

    filename: str
    content_type: str | None
    size: int
    category: str | None
    path: str


class ExtractedChunk(TypedDict, total=False):
    """Text (or failure) produced by one parser branch.

    Attributes:
        filename: Source file or synthetic id (e.g. description).
        parser: Parser implementation name.
        status: ``processed`` or ``failed``.
        text: Extracted plain text when successful.
        source_ref: Citation string for evidence merge.
        branch: LangGraph branch that produced this chunk.
    """

    filename: str
    parser: str
    status: str
    text: str
    source_ref: str
    branch: str


class AgentState(TypedDict):
    """Shared state passed between LangGraph nodes.

    List fields annotated with ``operator.add`` merge partial updates from
    parallel attachment branches.
    """

    request_id: str
    issue_key: str | None
    client: str | None
    description: str
    attachments: list[AttachmentMeta]
    attachment_statuses: Annotated[list[dict[str, Any]], operator.add]
    extracted_content: Annotated[list[ExtractedChunk], operator.add]
    merged_context: NotRequired[str]
    classification: NotRequired[dict[str, Any]]
    confidence: NotRequired[float]
    retry_count: int
    status: str
    errors: Annotated[list[dict[str, str]], operator.add]
    processing: NotRequired[dict[str, Any]]
    branches: NotRequired[dict[str, bool]]
    llm_calls: NotRequired[int]
    token_usage: NotRequired[dict[str, int]]