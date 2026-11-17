"""Secret and private-address redaction."""

from app.core.security import mask_secrets, sanitize_for_llm


def test_mask_secrets_redacts_password():
    assert "SuperSecret123" not in mask_secrets("password=SuperSecret123")


def test_mask_secrets_redacts_provider_tokens_and_pem_blocks():
    text = (
        "token: ghp_abcdefghijklmnopqrstuvwxyz0123456789\n"
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0123456789abcd\n"
        "-----END RSA PRIVATE KEY-----"
    )
    masked = mask_secrets(text)
    assert "ghp_" not in masked
    assert "PRIVATE KEY" not in masked
    assert "MIIEow" not in masked
    assert "[REDACTED_SECRET]" in masked


def test_sanitize_for_llm_masks_internal_ip():
    out = sanitize_for_llm("host 10.0.0.5 failed", mask_hosts=True)
    assert "10.0.0.5" not in out
    assert "[REDACTED_IP]" in out


def test_sanitize_can_keep_internal_ips():
    text = "host 10.0.0.5 failed"
    assert sanitize_for_llm(text, mask_hosts=False) == text
