from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    digest = hash_password("rahasia-kuat-123")
    assert digest != "rahasia-kuat-123"
    assert verify_password("rahasia-kuat-123", digest)
    assert not verify_password("salah-total", digest)


def test_session_tokens_are_unique_and_long() -> None:
    first = generate_session_token()
    second = generate_session_token()
    assert first != second
    assert len(first) >= 43


def test_session_token_hash_is_deterministic_sha256_hex() -> None:
    token = "contoh-token"
    assert hash_session_token(token) == hash_session_token(token)
    assert len(hash_session_token(token)) == 64
    assert hash_session_token(token) != token
