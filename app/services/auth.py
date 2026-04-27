import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException, status

from app.models.models import User, RefreshToken, PasswordHistory
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_jti, make_refresh_token_expiry,
)
from app.core.encryption import encrypt, decrypt, email_hash as compute_email_hash
from app.core.metrics import (
    auth_failures_total, token_rotations_total, token_family_revocations_total,
)
from app.core.logging import get_logger
from app.schemas.schemas import RegisterRequest, TokenResponse
from app.services.audit import AuditService

log = get_logger(__name__)

PASSWORD_HISTORY_DEPTH = 5


class AuthService:

    @staticmethod
    async def register(payload: RegisterRequest, db: AsyncSession) -> User:
        ehash = compute_email_hash(payload.email)
        result = await db.execute(select(User).where(User.email_hash == ehash))
        if result.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already registered")

        hpw = hash_password(payload.password)
        user = User(
            email=encrypt(payload.email),
            email_hash=ehash,
            hashed_password=hpw,
            name=encrypt(payload.name),
            role=payload.role,
        )
        db.add(user)
        await db.flush()

        db.add(PasswordHistory(user_id=user.id, hashed_password=hpw))
        await db.commit()
        await db.refresh(user)
        user.email = payload.email
        user.name = payload.name
        log.info("User registered", extra={"user_id": str(user.id)})
        return user

    @staticmethod
    async def login(email: str, password: str, db: AsyncSession) -> TokenResponse:
        ehash = compute_email_hash(email)
        result = await db.execute(select(User).where(User.email_hash == ehash))
        user: User | None = result.scalar_one_or_none()

        if not user or not verify_password(password, user.hashed_password):
            auth_failures_total.labels(reason="bad_credentials").inc()
            await AuditService.log(
                db, action="AUTH_FAILURE",
                details={"reason": "bad_credentials"},
            )
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        access_token = create_access_token(user.id, user.role)
        return await AuthService._issue_refresh_token(user, db, access_token, new_family=True)

    @staticmethod
    async def change_password(
        user: User, current_password: str, new_password: str, db: AsyncSession
    ) -> None:
        if not verify_password(current_password, user.hashed_password):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Current password incorrect")

        result = await db.execute(
            select(PasswordHistory)
            .where(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.created_at.desc())
            .limit(PASSWORD_HISTORY_DEPTH)
        )
        history = result.scalars().all()
        for entry in history:
            if verify_password(new_password, entry.hashed_password):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Password was used in the last {PASSWORD_HISTORY_DEPTH} passwords",
                )

        new_hash = hash_password(new_password)
        user.hashed_password = new_hash
        db.add(PasswordHistory(user_id=user.id, hashed_password=new_hash))

        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id)
            .values(revoked=True)
        )
        await db.commit()

    @staticmethod
    async def refresh(jti: str, db: AsyncSession) -> TokenResponse:
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
    async def logout(jti: str, db: AsyncSession) -> None:
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_jti == jti)
        )
        token: RefreshToken | None = result.scalar_one_or_none()

        if not token:
            return

        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == token.family_id)
            .values(revoked=True)
        )
        await AuditService.log(
            db, action="LOGOUT",
            user_id=token.user_id,
            target=str(token.family_id),
        )
        await db.commit()
        log.info("User logged out — family revoked", extra={"user_id": str(token.user_id)})

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
