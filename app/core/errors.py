"""Stable, client-facing error messages.

Exception text is logged server-side and is not copied into API responses.
"""

CLASSIFICATION_FAILED = "Classification failed"
NOT_CONFIGURED = "JOEY_SYSTEMONE_URL is not configured"
REQUEST_TIMEOUT = "Request processing timed out"
