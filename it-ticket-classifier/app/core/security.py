import re
from pathlib import Path

# Magic bytes for common formats (partial verification)
SIGNATURES: dict[str, list[bytes]] = {
    "pdf": [b"%PDF"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "webp": [b"RIFF"],
    "zip_office": [b"PK\x03\x04"],
    "gzip": [b"\x1f\x8b"],
}

EXTENSION_TO_CATEGORY: dict[str, str] = {
    "pdf": "document",
    "docx": "document",
    "doc": "document",
    "xlsx": "spreadsheet",
    "xls": "spreadsheet",
    "csv": "spreadsheet",
    "pptx": "presentation",
    "ppt": "presentation",
    "vsdx": "diagram",
    "vsd": "diagram",
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "webp": "image",
    "txt": "text",
    "log": "text",
    "json": "structured",
    "xml": "structured",
    "yaml": "structured",
    "yml": "structured",
}

ALLOWED_EXTENSIONS = frozenset(EXTENSION_TO_CATEGORY.keys())

SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*\b", re.IGNORECASE),
    re.compile(r"\bapi[_-]?key\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\bpassword\s*[:=]\s*\S+", re.IGNORECASE),
]

INTERNAL_HOST_PATTERN = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3})\b"
)


def safe_extension(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").lower()


def validate_extension(filename: str) -> str | None:
    ext = safe_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        return f"Unsupported file extension: .{ext or '(none)'}"
    return None


def verify_file_signature(data: bytes, ext: str) -> bool:
    """Best-effort signature check; text formats have no magic bytes."""
    if ext in ("txt", "log", "csv", "json", "xml", "yaml", "yml"):
        return True
    if ext == "pdf":
        return data[:4] == b"%PDF"
    if ext in ("png",):
        return any(data.startswith(s) for s in SIGNATURES["png"])
    if ext in ("jpg", "jpeg"):
        return data[:3] == b"\xff\xd8\xff"
    if ext == "webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if ext in ("docx", "xlsx", "pptx", "vsdx"):
        return data[:4] == b"PK\x03\x04"
    # Legacy binary office / visio — allow with PK or OLE header
    if ext in ("doc", "xls", "ppt", "vsd"):
        return data[:4] in (b"PK\x03\x04", b"\xd0\xcf\x11\xe0")
    return len(data) > 0


def mask_secrets(text: str) -> str:
    masked = text
    for pattern in SECRET_PATTERNS:
        masked = pattern.sub("[REDACTED_SECRET]", masked)
    return masked


def mask_infrastructure(text: str, mask_hosts: bool = True) -> str:
    if not mask_hosts:
        return text
    return INTERNAL_HOST_PATTERN.sub("[REDACTED_IP]", text)


def sanitize_for_llm(text: str, mask_hosts: bool = True) -> str:
    return mask_infrastructure(mask_secrets(text), mask_hosts=mask_hosts)