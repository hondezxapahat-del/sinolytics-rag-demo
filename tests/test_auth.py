"""Unit tests for auth.py's pure crypto/token functions — deliberately does
not test create_user/authenticate_user, since those hit the database and
belong in a manual/integration check instead of a fast unit suite."""

import pytest

import auth


def test_password_hash_roundtrip():
    hashed = auth._hash_password("correct horse battery staple")
    assert auth._verify_password("correct horse battery staple", hashed) is True


def test_password_hash_rejects_wrong_password():
    hashed = auth._hash_password("correct horse battery staple")
    assert auth._verify_password("wrong password", hashed) is False


def test_access_token_roundtrip():
    token = auth.create_access_token(42)
    assert auth.decode_access_token(token) == 42


def test_decode_rejects_garbage_token():
    with pytest.raises(auth.AuthError):
        auth.decode_access_token("not.a.real.token")


def test_decode_rejects_token_signed_with_wrong_secret():
    import jwt as pyjwt

    bad_token = pyjwt.encode({"sub": "1"}, "wrong-secret", algorithm=auth.JWT_ALGORITHM)
    with pytest.raises(auth.AuthError):
        auth.decode_access_token(bad_token)
