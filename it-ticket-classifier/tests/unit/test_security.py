"""Unit tests for upload validation and content redaction helpers."""

from app.core.security import (
    mask_secrets,
    sanitize_for_llm,
    validate_extension,
    verify_file_signature,
)


def test_validate_extension_rejects_unknown():
    assert validate_extension("malware.exe") is not None


def test_mask_secrets_redacts_password():
    text = "password=SuperSecret123"
    assert "SuperSecret123" not in mask_secrets(text)


def test_verify_pdf_signature():
    assert verify_file_signature(b"%PDF-1.4", "pdf")


def test_sanitize_for_llm_masks_internal_ip():
    text = "host 10.0.0.5 failed"
    out = sanitize_for_llm(text, mask_hosts=True)
    assert "10.0.0.5" not in out