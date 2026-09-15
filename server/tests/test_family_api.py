"""Integration tests for Family and Multi-Profile API router."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.family import FamilyGroup, FamilyMember, FamilyRole
from app.models.user import User


@pytest.mark.asyncio
async def test_family_crud_and_overview(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    # 1. Create family
    res = await async_client.post(
        "/api/v1/family",
        json={"name": "Smith Household"},
        headers=auth_headers,
    )
    assert res.status_code == 201
    group_data = res.json()
    assert group_data["name"] == "Smith Household"
    assert len(group_data["members"]) == 1
    assert group_data["members"][0]["role"] == "owner"

    # 2. Get Overview
    overview_res = await async_client.get("/api/v1/family/overview", headers=auth_headers)
    assert overview_res.status_code == 200
    overview_data = overview_res.json()
    assert overview_data["group"]["name"] == "Smith Household"
    assert len(overview_data["members"]) == 1

    # 3. Invite member
    invite_res = await async_client.post(
        "/api/v1/family/members/invite",
        json={
            "email": "kiddo@example.com",
            "role": "child",
            "spending_limit_minor": 5000,
        },
        headers=auth_headers,
    )
    assert invite_res.status_code == 201
    member_data = invite_res.json()
    assert member_data["role"] == "child"
    assert member_data["spending_limit_minor"] == 5000
    member_id = member_data["id"]

    # 4. Patch member
    patch_res = await async_client.patch(
        f"/api/v1/family/members/{member_id}",
        json={"spending_limit_minor": 7500, "role": "member"},
        headers=auth_headers,
    )
    assert patch_res.status_code == 200
    patched = patch_res.json()
    assert patched["spending_limit_minor"] == 7500
    assert patched["role"] == "member"

    # 5. Delete member
    del_res = await async_client.delete(
        f"/api/v1/family/members/{member_id}",
        headers=auth_headers,
    )
    assert del_res.status_code == 204
