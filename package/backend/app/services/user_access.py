from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import User
from app.services.ai_service import AIService


LOCAL_USER_CARD_KEY = "__LOCAL_SINGLE_USER__"
LOCAL_USER_ACCESS_LINK = "local://workspace"


def is_local_user(user: User) -> bool:
    return user.card_key == LOCAL_USER_CARD_KEY


def get_or_create_local_user(db: Session) -> User:
    user = db.query(User).filter(User.card_key == LOCAL_USER_CARD_KEY).first()

    if not user:
        user = User(
            card_key=LOCAL_USER_CARD_KEY,
            access_link=LOCAL_USER_ACCESS_LINK,
            is_active=True,
            usage_limit=0,
            usage_count=0,
            last_used=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    if not user.is_active:
        user.is_active = True

    user.last_used = datetime.utcnow()
    db.commit()
    return user


def get_current_user(card_key: Optional[str], db: Session) -> User:
    if not card_key:
        return get_or_create_local_user(db)

    user = db.query(User).filter(
        User.card_key == card_key,
        User.is_active.is_(True),
    ).first()

    if not user:
        raise HTTPException(status_code=401, detail="无效的卡密")

    user.last_used = datetime.utcnow()
    db.commit()
    return user


def check_usage_limit(user: User) -> None:
    if is_local_user(user):
        return

    usage_limit = user.usage_limit if user.usage_limit is not None else settings.DEFAULT_USAGE_LIMIT
    usage_count = user.usage_count or 0
    if usage_limit > 0 and usage_count >= usage_limit:
        raise HTTPException(status_code=403, detail="该卡密已达到使用次数限制")


def increment_usage(user: User, db: Session) -> None:
    if is_local_user(user):
        return

    current_count = user.usage_count or 0
    user.usage_count = current_count + 1
    db.commit()


def get_ai_service() -> AIService:
    return AIService(
        model=settings.POLISH_MODEL or "gpt-5",
        api_key=settings.POLISH_API_KEY or settings.OPENAI_API_KEY,
        base_url=settings.POLISH_BASE_URL or settings.OPENAI_BASE_URL,
    )
