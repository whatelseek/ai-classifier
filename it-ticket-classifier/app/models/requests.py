"""Inbound request dataclasses used after HTTP multipart parsing."""

from dataclasses import dataclass


@dataclass(slots=True)
class UploadedAttachment:
    """One file attachment buffered in memory for validation and parsing.

    Attributes:
        filename: Original client filename.
        content_type: MIME type from the upload, if provided.
        data: Raw file bytes.
        size: Byte length of ``data``.
    """

    filename: str
    content_type: str | None
    data: bytes
    size: int


@dataclass(slots=True)
class ClassifyRequestPayload:
    """Normalized classification input independent of HTTP/Jira transport.

    Attributes:
        description: Ticket narrative text.
        issue_key: Optional external ticket id.
        client: Optional customer or tenant id.
        attachments: Zero or more uploaded files.
    """

    description: str | None
    issue_key: str | None
    client: str | None
    attachments: list[UploadedAttachment]