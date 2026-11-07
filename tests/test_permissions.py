"""
Automated RBAC Permission & Role Hierarchy Tests (`tests/test_permissions.py`).
Tests:
- Server-side permission enforcement
- Anti-privilege escalation (moderator cannot grant administrator)
- Self-admin grant prevention (nobody can grant themselves administrator via RBAC)
- Bot Owner and Server Owner protection
- Discord role hierarchy enforcement (moderators cannot act against equal or higher roles)
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bot.core.discord_compat import discord
from bot.core.error_handler import PrivilegeEscalationError
from bot.database.manager import DatabaseManager
from bot.database.models import PermissionLevel
from bot.services.permission_service import PermissionService
from bot.utils.validators import validate_assignable_role, validate_role_hierarchy


class TestPermissionsAndHierarchy(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.tmp_dir.name) / "perm_test.db")
        await self.db.connect()
        self.bot_owner_id = 999000111
        self.perm_service = PermissionService(self.db, bot_owner_id=self.bot_owner_id)

        self.guild = discord.Guild(id=777, name="RBAC Guild", owner_id=1000)
        self.admin_role = discord.Role(id=10, name="Admin", position=30, permissions=discord.Permissions(administrator=True))
        self.mod_role = discord.Role(id=20, name="Moderator", position=20, permissions=discord.Permissions(moderate_members=True))
        self.member_role = discord.Role(id=30, name="Member", position=5)

        self.owner_member = discord.Member(id=1000, name="ServerOwner", guild=self.guild, roles=[self.admin_role])
        self.admin_member = discord.Member(
            id=2000,
            name="AdminUser",
            guild=self.guild,
            roles=[self.admin_role],
            guild_permissions=discord.Permissions(administrator=True),
        )
        self.mod_member = discord.Member(
            id=3000,
            name="ModUser",
            guild=self.guild,
            roles=[self.mod_role],
            guild_permissions=discord.Permissions(moderate_members=True),
        )
        self.regular_member = discord.Member(
            id=4000,
            name="RegularUser",
            guild=self.guild,
            roles=[self.member_role],
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.tmp_dir.cleanup()

    async def test_prevent_self_admin_grant(self) -> None:
        with self.assertRaises(PrivilegeEscalationError):
            await self.perm_service.add_user_permission(
                guild=self.guild,
                actor=self.admin_member,
                user_id=self.admin_member.id,
                level=PermissionLevel.ADMIN.value,
            )

    async def test_prevent_privilege_escalation_by_moderator(self) -> None:
        with self.assertRaises(PrivilegeEscalationError):
            await self.perm_service.add_role_permission(
                guild=self.guild,
                actor=self.mod_member,
                role_id=self.member_role.id,
                level=PermissionLevel.ADMIN.value,
            )

    async def test_protect_bot_owner_and_server_owner(self) -> None:
        with self.assertRaises(PrivilegeEscalationError):
            await self.perm_service.remove_user_permission(
                guild=self.guild,
                actor=self.admin_member,
                user_id=self.bot_owner_id,
                level=PermissionLevel.MODERATOR.value,
            )

    async def test_role_hierarchy_enforcement(self) -> None:
        # Mod cannot target Admin (higher role)
        ok_higher, _ = validate_role_hierarchy(self.mod_member, self.admin_member, self.guild, self.bot_owner_id)
        self.assertFalse(ok_higher)

        # Mod cannot target another Mod with equal top role
        other_mod = discord.Member(id=3001, name="OtherMod", guild=self.guild, roles=[self.mod_role])
        ok_equal, _ = validate_role_hierarchy(self.mod_member, other_mod, self.guild, self.bot_owner_id)
        self.assertFalse(ok_equal)

        # Mod can target regular member with lower role
        ok_lower, _ = validate_role_hierarchy(self.mod_member, self.regular_member, self.guild, self.bot_owner_id)
        self.assertTrue(ok_lower)

    async def test_assignable_role_below_bot_highest_role(self) -> None:
        # Bot top_role is at position 50 in FakeGuild
        above_bot_role = discord.Role(id=99, name="SuperRole", position=60)
        ok_above, _ = validate_assignable_role(above_bot_role, self.guild)
        self.assertFalse(ok_above)

        ok_below, _ = validate_assignable_role(self.member_role, self.guild)
        self.assertTrue(ok_below)


if __name__ == "__main__":
    unittest.main()
