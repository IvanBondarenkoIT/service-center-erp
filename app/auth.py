from __future__ import annotations

from passlib.context import CryptContext
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def make_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="scerp-session")


def create_session_token(user_id: int) -> str:
    return make_serializer().dumps({"uid": user_id})


def load_session_token(token: str) -> int | None:
    settings = get_settings()
    try:
        data = make_serializer().loads(token, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid")
    return int(uid) if uid is not None else None
