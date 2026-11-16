"""Stable, client-facing error messages.

Exception text is logged server-side and is not copied into API responses.
"""

EXTRACTION_FAILED = "Attachment could not be parsed"
ARCHIVE_TOO_LARGE = "Archive exceeds safe decompression limit"
INVALID_ARCHIVE = "Attachment is not a valid archive"
CLASSIFICATION_FAILED = "The model could not classify this ticket"
INTERNAL_ERROR = "Classification failed"
REQUEST_TIMEOUT = "Request processing timed out"
