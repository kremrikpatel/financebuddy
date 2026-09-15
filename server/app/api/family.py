"""Family and Household Sharing API Router.

Implements multi-profile control:
- Family group creation and management
- Role-based access control (owner, admin, member, child)
- Member invitation and role/limit updates
- Real-time monthly spending aggregation per member and household total
"""
from __future__ import annotations

from datetime import date, datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.family import FamilyGroup, FamilyMember, FamilyRole
from app.models.finance import Transaction
from app.models.user import User
from app.services.deps import get_current_user

router = APIRouter(prefix="/family", tags=["family"])


# ── Schemas ─────────────────────────────────────────────────────────────

class FamilyCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class FamilyMemberInviteIn(BaseModel):
    email: EmailStr
    role: FamilyRole = FamilyRole.MEMBER
    spending_limit_minor: int | None = None
    family_id: uuid.UUID | None = None


class FamilyMemberUpdateIn(BaseModel):
    role: FamilyRole | None = None
    spending_limit_minor: int | None = None
    is_active: bool | None = None


class FamilyMemberOut(BaseModel):
    id: str
    user_id: str
    name: str
    email: str
    role: str
    spending_limit_minor: int | None
    spent_this_month_minor: int = 0
    is_active: bool
    joined_at: datetime | None = None

    model_config = {"from_attributes": True}


class FamilyGroupOut(BaseModel):
    id: str
    name: str
    owner_id: str
    created_at: datetime
    members: list[FamilyMemberOut] = []

    model_config = {"from_attributes": True}


class FamilyOverviewOut(BaseModel):
    group: dict
    members: list[FamilyMemberOut]
    total_spent_minor: int


# ── Helpers ─────────────────────────────────────────────────────────────

async def _get_user_family_membership(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[FamilyGroup | None, FamilyMember | None]:
    """Find the active family group and membership for a user."""
    stmt = (
        select(FamilyMember)
        .options(selectinload(FamilyMember.family).selectinload(FamilyGroup.members).selectinload(FamilyMember.user))
        .where(FamilyMember.user_id == user_id, FamilyMember.is_active.is_(True))
    )
    membership = await db.scalar(stmt)
    if membership and membership.family:
        return membership.family, membership

    # Check if user owns a group directly
    group_stmt = (
        select(FamilyGroup)
        .options(selectinload(FamilyGroup.members).selectinload(FamilyMember.user))
        .where(FamilyGroup.owner_id == user_id)
    )
    group = await db.scalar(group_stmt)
    if group:
        # Find or return owner membership
        for m in group.members:
            if m.user_id == user_id:
                return group, m
        return group, None

    return None, None


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("", response_model=FamilyGroupOut, status_code=status.HTTP_201_CREATED)
async def create_family_group(
    body: FamilyCreateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new family group and make the current user the owner."""
    # Check if user already owns or belongs to a family
    existing_group, _ = await _get_user_family_membership(db, user.id)
    if existing_group and existing_group.owner_id == user.id:
        # Return existing group or allow creating new
        pass

    group = FamilyGroup(name=body.name.strip(), owner_id=user.id)
    db.add(group)
    await db.flush()

    # Add creator as owner member
    owner_member = FamilyMember(
        family_id=group.id,
        user_id=user.id,
        role=FamilyRole.OWNER,
        is_active=True,
    )
    db.add(owner_member)
    await db.commit()
    await db.refresh(group)

    return {
        "id": str(group.id),
        "name": group.name,
        "owner_id": str(group.owner_id),
        "created_at": group.created_at,
        "members": [
            FamilyMemberOut(
                id=str(owner_member.id),
                user_id=str(user.id),
                name=user.full_name or user.email,
                email=user.email,
                role=owner_member.role.value if hasattr(owner_member.role, "value") else str(owner_member.role),
                spending_limit_minor=owner_member.spending_limit_minor,
                spent_this_month_minor=0,
                is_active=owner_member.is_active,
                joined_at=owner_member.joined_at,
            )
        ],
    }


@router.get("/overview", response_model=FamilyOverviewOut)
async def get_family_overview(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return family group overview with role badges, limits, and monthly spending per member."""
    group, current_membership = await _get_user_family_membership(db, user.id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active family group found for user. Create one first.",
        )

    # First day of the current calendar month
    today = date.today()
    start_of_month = date(today.year, today.month, 1)

    members_stmt = (
        select(FamilyMember)
        .options(selectinload(FamilyMember.user))
        .where(FamilyMember.family_id == group.id)
        .order_by(FamilyMember.created_at)
    )
    members = list((await db.execute(members_stmt)).scalars().all())

    total_household_spend = 0
    member_outputs: list[FamilyMemberOut] = []

    for m in members:
        # Sum spending this month for member
        spend_stmt = (
            select(func.sum(Transaction.amount_minor))
            .where(
                Transaction.user_id == m.user_id,
                Transaction.date >= start_of_month,
                Transaction.is_income.is_(False),
                Transaction.excluded.is_(False),
            )
        )
        raw_spent = await db.scalar(spend_stmt)
        spent_minor = abs(raw_spent) if raw_spent else 0
        total_household_spend += spent_minor

        u_name = m.user.full_name if m.user and m.user.full_name else (m.user.email if m.user else "Member")
        u_email = m.user.email if m.user else ""

        member_outputs.append(
            FamilyMemberOut(
                id=str(m.id),
                user_id=str(m.user_id),
                name=u_name,
                email=u_email,
                role=m.role.value if hasattr(m.role, "value") else str(m.role),
                spending_limit_minor=m.spending_limit_minor,
                spent_this_month_minor=spent_minor,
                is_active=m.is_active,
                joined_at=m.joined_at,
            )
        )

    return FamilyOverviewOut(
        group={
            "id": str(group.id),
            "name": group.name,
            "owner_id": str(group.owner_id),
            "created_at": group.created_at,
        },
        members=member_outputs,
        total_spent_minor=total_household_spend,
    )


@router.post("/members/invite", response_model=FamilyMemberOut, status_code=status.HTTP_201_CREATED)
async def invite_family_member(
    body: FamilyMemberInviteIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Invite or add a user to the family group with a designated role and spending limit."""
    group, caller_membership = await _get_user_family_membership(db, user.id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Family group not found. Please create a family group first.",
        )

    # Permission check: Only owner or admin can invite
    is_owner = group.owner_id == user.id or (caller_membership and caller_membership.role == FamilyRole.OWNER)
    is_admin = caller_membership and caller_membership.role == FamilyRole.ADMIN
    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only family owners and administrators can invite new members.",
        )

    # Find the target user by email
    target_user = await db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if not target_user:
        # Create a placeholder user account for invitation
        target_user = User(
            email=body.email.lower().strip(),
            full_name=body.email.split("@")[0].capitalize(),
            locale="en",
            base_currency="AUD",
            is_active=True,
        )
        db.add(target_user)
        await db.flush()

    # Check if already a member
    existing_m = await db.scalar(
        select(FamilyMember).where(
            FamilyMember.family_id == group.id,
            FamilyMember.user_id == target_user.id,
        )
    )
    if existing_m:
        if not existing_m.is_active:
            existing_m.is_active = True
            existing_m.role = body.role
            existing_m.spending_limit_minor = body.spending_limit_minor
            await db.commit()
            await db.refresh(existing_m)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User {body.email} is already a member of this family group.",
            )
        member = existing_m
    else:
        member = FamilyMember(
            family_id=group.id,
            user_id=target_user.id,
            role=body.role,
            spending_limit_minor=body.spending_limit_minor,
            is_active=True,
        )
        db.add(member)
        await db.commit()
        await db.refresh(member)

    return FamilyMemberOut(
        id=str(member.id),
        user_id=str(target_user.id),
        name=target_user.full_name or target_user.email,
        email=target_user.email,
        role=member.role.value if hasattr(member.role, "value") else str(member.role),
        spending_limit_minor=member.spending_limit_minor,
        spent_this_month_minor=0,
        is_active=member.is_active,
        joined_at=member.joined_at,
    )


@router.patch("/members/{member_id}", response_model=FamilyMemberOut)
async def update_family_member(
    member_id: uuid.UUID,
    body: FamilyMemberUpdateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update role, spending limit, or active status of a family member."""
    member = await db.scalar(
        select(FamilyMember)
        .options(selectinload(FamilyMember.family), selectinload(FamilyMember.user))
        .where(FamilyMember.id == member_id)
    )
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Family member not found.",
        )

    # Permission check: Caller must be owner or admin of the family
    caller_m = await db.scalar(
        select(FamilyMember).where(
            FamilyMember.family_id == member.family_id,
            FamilyMember.user_id == user.id,
        )
    )
    is_owner = member.family.owner_id == user.id or (caller_m and caller_m.role == FamilyRole.OWNER)
    is_admin = caller_m and caller_m.role == FamilyRole.ADMIN

    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to update family members.",
        )

    # Admins cannot alter owner's role or demote owners
    if member.role == FamilyRole.OWNER and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify family group owner.",
        )

    if body.role is not None:
        member.role = body.role
    if body.spending_limit_minor is not None:
        member.spending_limit_minor = body.spending_limit_minor
    if body.is_active is not None:
        member.is_active = body.is_active

    await db.commit()
    await db.refresh(member)

    u_name = member.user.full_name if member.user and member.user.full_name else (member.user.email if member.user else "")
    u_email = member.user.email if member.user else ""

    return FamilyMemberOut(
        id=str(member.id),
        user_id=str(member.user_id),
        name=u_name,
        email=u_email,
        role=member.role.value if hasattr(member.role, "value") else str(member.role),
        spending_limit_minor=member.spending_limit_minor,
        spent_this_month_minor=0,
        is_active=member.is_active,
        joined_at=member.joined_at,
    )


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_family_member(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a member from the family group."""
    member = await db.scalar(
        select(FamilyMember)
        .options(selectinload(FamilyMember.family))
        .where(FamilyMember.id == member_id)
    )
    if not member:
        return None

    # Permission check: owner/admin or self removal
    caller_m = await db.scalar(
        select(FamilyMember).where(
            FamilyMember.family_id == member.family_id,
            FamilyMember.user_id == user.id,
        )
    )
    is_self = member.user_id == user.id
    is_owner = member.family.owner_id == user.id or (caller_m and caller_m.role == FamilyRole.OWNER)
    is_admin = caller_m and caller_m.role == FamilyRole.ADMIN

    if not (is_self or is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to remove this family member.",
        )

    # Cannot delete the group owner
    if member.role == FamilyRole.OWNER and member.family.owner_id == member.user_id and not is_self:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the owner of the family group.",
        )

    await db.delete(member)
    await db.commit()
    return None
