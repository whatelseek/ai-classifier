"""Upload validation, file signatures, and redaction before LLM submission."""

import io
import re
import zipfile
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

# Office and Visio packages are ZIP archives. Reject declared uncompressed
# sizes above this limit before any parser inflates the payload.
MAX_ZIP_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
ZIP_EXTENSIONS = frozenset({"docx", "xlsx", "pptx", "vsdx"})


class UnsafeArchiveError(ValueError):
    """Raised when a ZIP payload declares an unsafe uncompressed size."""

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
    """Return the normalized lowercase extension without a leading dot.

    Args:
        filename: Original upload filename.

    Returns:
        Extension string or empty string when absent.
    """
    return Path(filename).suffix.lstrip(".").lower()


def validate_extension(filename: str) -> str | None:
    """Check whether the filename extension is allowed.

    Args:
        filename: Original upload filename.

    Returns:
        Error message if unsupported; otherwise ``None``.
    """
    ext = safe_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        return f"Unsupported file extension: .{ext or '(none)'}"
    return None


def verify_file_signature(data: bytes, ext: str) -> bool:
    """Best-effort magic-byte verification for binary formats.

    Text-like extensions skip signature checks. Legacy Office binaries accept
    OLE or ZIP headers.

    Args:
        data: Raw file bytes.
        ext: Normalized extension.

    Returns:
        True when the signature matches or the format is exempt.
    """
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
    if ext in ("doc", "xls", "ppt", "vsd"):
        return data[:4] in (b"PK\x03\x04", b"\xd0\xcf\x11\xe0")
    return len(data) > 0


def mask_secrets(text: str) -> str:
    """Replace detected secrets and credentials with a redaction token.

    Args:
        text: Raw text that may contain sensitive material.

    Returns:
        Redacted text safe for external model APIs.
    """
    masked = text
    for pattern in SECRET_PATTERNS:
        masked = pattern.sub("[REDACTED_SECRET]", masked)
    return masked


def mask_infrastructure(text: str, mask_hosts: bool = True) -> str:
    """Mask private RFC1918 addresses when policy requires it.

    Args:
        text: Input text.
        mask_hosts: When False, return text unchanged.

    Returns:
        Text with private IPs replaced when masking is enabled.
    """
    if not mask_hosts:
        return text
    return INTERNAL_HOST_PATTERN.sub("[REDACTED_IP]", text)


def assert_zip_archive_safe(
    data: bytes, *, limit: int = MAX_ZIP_UNCOMPRESSED_BYTES
) -> None:
    """Reject ZIP payloads whose declared uncompressed size exceeds ``limit``.

    The check reads the central directory only. It does not inflate entries.

    Args:
        data: Raw archive bytes.
        limit: Maximum total declared uncompressed size in bytes.

    Raises:
        ValueError: When ``data`` is not a ZIP archive.
        UnsafeArchiveError: When the declared uncompressed size exceeds ``limit``.
    """
    buffer = io.BytesIO(data)
    if not zipfile.is_zipfile(buffer):
        raise ValueError("File is not a valid ZIP archive")
    buffer.seek(0)
    with zipfile.ZipFile(buffer) as archive:
        total = sum(info.file_size for info in archive.infolist())
    if total > limit:
        raise UnsafeArchiveError(
            f"Archive uncompressed size {total} exceeds limit {limit}"
        )


def sanitize_for_llm(text: str, mask_hosts: bool = True) -> str:
    """Apply secret and infrastructure masking before LLM prompts.

    Args:
        text: Extracted or user-provided content.
        mask_hosts: Whether to mask private IP addresses.

    Returns:
        Sanitized content.
    """
    return mask_infrastructure(mask_secrets(text), mask_hosts=mask_hosts)