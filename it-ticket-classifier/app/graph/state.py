import operator
from typing import Annotated, Any, NotRequired, TypedDict


class AttachmentMeta(TypedDict):
    filename: str
    content_type: str | None
    size: int
    category: str | None
    path: str  # temp file path


class ExtractedChunk(TypedDict, total=False):
    filename: str
    parser: str
    status: str
    text: str
    source_ref: str
    branch: str


class AgentState(TypedDict):
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