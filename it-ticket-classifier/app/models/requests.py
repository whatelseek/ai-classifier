from dataclasses import dataclass


@dataclass(slots=True)
class UploadedAttachment:
    filename: str
    content_type: str | None
    data: bytes
    size: int


@dataclass(slots=True)
class ClassifyRequestPayload:
    description: str | None
    issue_key: str | None
    client: str | None
    attachments: list[UploadedAttachment]