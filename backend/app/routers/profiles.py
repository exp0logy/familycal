"""
app/routers/profiles.py — CRUD for family member profiles.

Routes:
  GET    /api/profiles           → Profile[]
  POST   /api/profiles           → Profile
  PATCH  /api/profiles/{id}      → Profile
  DELETE /api/profiles/{id}      → 204
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.models import Profile
from app.schemas import ProfileCreate, ProfileRead, ProfileUpdate

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfileRead])
async def list_profiles(session: AsyncSession = Depends(get_session)) -> list[Profile]:
    """Return all profiles ordered by creation date."""
    result = await session.execute(select(Profile).order_by(Profile.created_at))
    return result.scalars().all()


@router.post("", response_model=ProfileRead, status_code=status.HTTP_201_CREATED)
async def create_profile(
    body: ProfileCreate,
    session: AsyncSession = Depends(get_session),
) -> Profile:
    """Create a new profile."""
    profile = Profile(name=body.name, color=body.color, emoji=body.emoji)
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


@router.patch("/{profile_id}", response_model=ProfileRead)
async def update_profile(
    profile_id: int,
    body: ProfileUpdate,
    session: AsyncSession = Depends(get_session),
) -> Profile:
    """Update mutable fields on an existing profile."""
    result = await session.execute(select(Profile).where(Profile.id == profile_id))
    profile: Profile | None = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    if body.name is not None:
        profile.name = body.name
    if body.color is not None:
        profile.color = body.color
    if body.emoji is not None:
        profile.emoji = body.emoji

    await session.commit()
    await session.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a profile by ID."""
    result = await session.execute(select(Profile).where(Profile.id == profile_id))
    profile: Profile | None = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    await session.delete(profile)
    await session.commit()
