import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException, status

from app.models.models import User, RefreshToken
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_jti, make_refresh_token_expiry,
)
from app.core.metrics import (
    auth_failures_total, token_rotations_total, token_family_revocations_total,
)
from app.core.logging import get_logger
from app.schemas.schemas import RegisterRequest, TokenResponse
from app.services.audit import AuditService

log = get_logger(__name__)


class AuthService:

    @staticmethod
    async def register(payload: RegisterRequest, db: AsyncSession) -> User:
        result = await db.execute(select(User).where(User.email == payload.email))
        if result.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already registered")

        user = User(
            email=payload.email,
            hashed_password=hash_password(payload.password),
            name=payload.name,
            role=payload.role,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        log.info("User registered", extra={"user_id": str(user.id)})
        return user

    @staticmethod
    async def login(email: str, password: str, db: AsyncSession) -> TokenResponse:
        result = await db.execute(select(User).where(User.email == email))
        user: User | None = result.scalar_one_or_none()

        if not user or not verify_password(password, user.hashed_password):
            auth_failures_total.labels(reason="bad_credentials").inc()
            await AuditService.log(
                db, action="AUTH_FAILURE",
                details={"reason": "bad_credentials", "email": email}
            )
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        access_token = create_access_token(user.id, user.role)
        return await AuthService._issue_refresh_token(user, db, access_token, new_family=True)

    @staticmethod
    async def refresh(jti: str, db: AsyncSession) -> TokenResponse:
        """
        Rotate refresh token. On reuse of a consumed token, revoke the entire family.
        """
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_jti == jti)
        )
        token: RefreshToken | None = result.scalar_one_or_none()

        if not token or token.revoked:
            auth_failures_total.labels(reason="token_invalid").inc()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        if token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            auth_failures_total.labels(reason="token_expired").inc()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

        # ── Reuse detection: token was already used → revoke entire family ──
        if token.used_at is not None:
            auth_failures_total.labels(reason="token_reuse").inc()
            token_family_revocations_total.inc()
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == token.family_id)
                .values(revoked=True)
            )
            await db.commit()
            log.warning(
                "Refresh token reuse detected — family revoked",
                extra={"user_id": str(token.user_id), "family_id": str(token.family_id)},
            )
            await AuditService.log(
                db, action="TOKEN_FAMILY_REVOKED",
                user_id=token.user_id,
                target=str(token.family_id),
                details={"reason": "reuse_detected"},
            )
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token reuse detected. Please log in again.")

        # Mark current token as used
        token.used_at = datetime.now(timezone.utc)
        await db.flush()

        result = await db.execute(select(User).where(User.id == token.user_id))
        user: User = result.scalar_one()

        access_token = create_access_token(user.id, user.role)
        token_rotations_total.inc()
        return await AuthService._issue_refresh_token(
            user, db, access_token, new_family=False, family_id=token.family_id
        )

    @staticmethod
    async def _issue_refresh_token(
        user: User,
        db: AsyncSession,
        access_token: str,
        new_family: bool,
        family_id: uuid.UUID | None = None,
    ) -> TokenResponse:
        jti = create_refresh_jti()
        fid = uuid.uuid4() if new_family else (family_id or uuid.uuid4())

        rt = RefreshToken(
            user_id=user.id,
            family_id=fid,
            token_jti=jti,
            expires_at=make_refresh_token_expiry(),
        )
        db.add(rt)
        await db.commit()

        return TokenResponse(access_token=access_token, refresh_token=jti)
