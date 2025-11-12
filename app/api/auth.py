from __future__ import annotations

from typing import Optional
import os

from fastapi import Depends, HTTPException, Request, status

try:  # Optional dependency; only required when JWT enforcement is enabled
    import jwt  # type: ignore
except Exception:  # pragma: no cover
    jwt = None  # type: ignore


class User:
    def __init__(self, subject: str | None) -> None:
        self.sub = subject


def _extract_bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    return auth.split(" ", 1)[1].strip() or None


async def jwt_optional(request: Request) -> User | None:
    """Accepts JWT when provided. If ENFORCE_JWT is falsey (default), allows missing token in dev.

    Configuration via env:
      - ENFORCE_JWT: when truthy, require a valid token on protected routes
      - AUTH_JWT_SECRET: HS256 secret for token verification (optional if not enforcing)
      - AUTH_JWT_AUDIENCE / AUTH_JWT_ISSUER: optional claims to validate
    """
    enforce = os.getenv("ENFORCE_JWT", "").lower() in {"1", "true", "yes"}
    token = _extract_bearer_token(request)
    if not token:
        # No token supplied
        if enforce:
            return None
        # Dev default: anonymous user allowed on protected routes unless enforce is enabled
        return User(subject="anonymous")

    secret = os.getenv("AUTH_JWT_SECRET")
    audience = os.getenv("AUTH_JWT_AUDIENCE")
    issuer = os.getenv("AUTH_JWT_ISSUER")
    if secret and jwt:
        try:
            options = {"verify_aud": bool(audience)}
            decoded = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience=audience if audience else None,
                issuer=issuer if issuer else None,
                options=options,
            )
            sub = decoded.get("sub") or decoded.get("subject") or "user"
            return User(subject=str(sub))
        except Exception:
            # Invalid token
            return None
    # If no secret configured, accept any non-empty token in dev
    return User(subject="dev-user")


async def jwt_required(user: User | None = Depends(jwt_optional)) -> User:
    """Require a valid user. When ENFORCE_JWT=true, a missing/invalid token will raise 401.
    In dev (default), anonymous is accepted to avoid blocking local tests and UI while wiring auth.
    """
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid token")
    return user
