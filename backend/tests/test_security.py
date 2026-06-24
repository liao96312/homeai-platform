from backend.app.core.security import hash_password, verify_password


def test_password_hash_uses_current_iteration_format():
    hashed = hash_password("correct horse battery staple", salt="abc123")

    parts = hashed.split("$")
    assert parts[0] == "pbkdf2_sha256"
    assert int(parts[1]) >= 600_000
    assert parts[2] == "abc123"
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_verify_password_accepts_legacy_120k_hashes():
    legacy = "pbkdf2_sha256$abc123$caee5029337f22ed1f29f98ff7d470ddb54e2b1640f7973a3983dfa3899de6de"

    assert verify_password("correct horse battery staple", legacy) is True
