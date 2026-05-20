"""Test password redaction helper."""

from voulezvous.config import redact_passwords


def test_redact_passwords():
    """Test that password redaction removes sensitive patterns."""
    # Test password patterns
    assert "password" in "password: secret123"
    assert "[REDACTED]" in redact_passwords("password: secret123")
    assert "[REDACTED]" in redact_passwords("password='secret123'")
    assert "[REDACTED]" in redact_passwords('password="secret123"')

    # Test credential_password patterns
    assert "[REDACTED]" in redact_passwords("credential_password: mypass")
    assert "[REDACTED]" in redact_passwords("credential_password='mypass'")

    # Test secret patterns
    assert "[REDACTED]" in redact_passwords("secret: mysecret")
    assert "[REDACTED]" in redact_passwords("secret='mysecret'")

    # Test token patterns
    assert "[REDACTED]" in redact_passwords("token: abc123xyz")
    assert "[REDACTED]" in redact_passwords("token='abc123xyz'")

    # Test api_key patterns
    assert "[REDACTED]" in redact_passwords("api_key: xyz789")
    assert "[REDACTED]" in redact_passwords("api_key='xyz789'")

    # Test case insensitivity
    assert "[REDACTED]" in redact_passwords("PASSWORD: secret123")
    assert "[REDACTED]" in redact_passwords("CREDENTIAL_PASSWORD: mypass")

    # Test that non-sensitive text is preserved
    text = "user@example.com logged in successfully"
    assert text == redact_passwords(text)

    # Test mixed content
    mixed = "user@example.com logged in with password: secret123"
    assert "user@example.com" in redact_passwords(mixed)
    assert "[REDACTED]" in redact_passwords(mixed)
    assert "secret123" not in redact_passwords(mixed)
