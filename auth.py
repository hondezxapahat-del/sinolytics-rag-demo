"""Lightweight username+password auth (PRD_v1.1.md Goal 8): just enough to
own a conversation history — no roles, no password recovery, no email
verification. Password hashing (bcrypt) and session tokens (JWT) only."""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from dotenv import load_dotenv

from retrieval import supabase

load_dotenv()

JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
JWT_ALGORITHM = "HS256"
TOKEN_LIFETIME = timedelta(days=30)

# Lightweight, not a full complexity policy (uppercase/digits/symbols) — this
# product deliberately has no password recovery, so a slightly higher floor
# than "test" reduces trivially-guessable accounts without adding friction
# disproportionate to a demo-scale login.
MIN_PASSWORD_LENGTH = 8


class AuthError(Exception):
    """Bad credentials, duplicate username, weak password, or an
    invalid/expired token."""


def _hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password, password_hash):
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_user(username, password):
    if not username or not username.strip():
        raise AuthError("Username cannot be empty.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")

    existing = supabase.table("users").select("id").eq("username", username).execute()
    if existing.data:
        raise AuthError("That username is already taken.")

    result = (
        supabase.table("users")
        .insert({"username": username, "password_hash": _hash_password(password)})
        .execute()
    )
    return result.data[0]


def authenticate_user(username, password):
    result = supabase.table("users").select("*").eq("username", username).execute()
    if not result.data or not _verify_password(password, result.data[0]["password_hash"]):
        raise AuthError("Incorrect username or password.")
    return result.data[0]


def create_access_token(user_id):
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + TOKEN_LIFETIME,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token):
    """Returns the user_id encoded in the token, or raises AuthError."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid or expired session — please log in again.") from exc
