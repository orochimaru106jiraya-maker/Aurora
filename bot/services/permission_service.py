"""
Centralized Role-Based Access Control (RBAC) Service for Cosmic ki baddie.

Security Guarantees:
1. Server-side validation on every command and interactive dashboard action (UI visibility is never the sole guard).
2. Prevents privilege escalation: No user can grant a permission level equal to or higher than their own effective level
   (except Server Owner / Bot Owner).
3. Never allows a user to grant themselves `administrator` permissions.
4. Protects the Bot Owner and Server Owner from having their permissions removed or overridden.
5. Evaluates Discord native permissions (`administrator`, `manage_guild`, `moderate_members`) alongside custom RBAC roles,
   individual user grants, command-specific overrides, and module-specific rules.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from bot.core.discord_compat import discord
from bot.core.error_handler import PrivilegeEscalationError
from bot.database.manager import DatabaseManager
from bot.database.models import PERMISSION_HIERARCHY, PermissionLevel

logger = logging.getLogger("cosmic.services.permission")


class PermissionService:
    """Centralized RBAC engine used by all 12 Cogs and interactive UI views."""

    def __init__(self, db: DatabaseManager, bot_owner_id: int) -> None:
        self.db = db
        self.bot_owner_id = int(bot_owner_id)

    async def get_member_effective_level(self, guild: Any, member: Any) -> PermissionLevel:
        """Compute the highest PermissionLevel held by a member in a guild."""
        user_id = int(getattr(member, "id", 0))
        if user_id == self.bot_owner_id:
            return PermissionLevel.BOT_OWNER

        if guild is not None and user_id == int(getattr(guild, "owner_id", 0)):
            return PermissionLevel.SERVER_OWNER

        # Native Discord Administrator permission
        guild_perms = getattr(member, "guild_permissions", None)
        if guild_perms and getattr(guild_perms, "administrator", False):
            return PermissionLevel.ADMIN

        if guild is None:
            return PermissionLevel.EVERYONE

        guild_id = int(guild.id)
        highest_score = PERMISSION_HIERARCHY[PermissionLevel.EVERYONE.value]
        best_level = PermissionLevel.EVERYONE

        # Check explicit user permission mappings in SQLite
        user_rows = await self.db.fetch_all(
            "SELECT permission_level FROM rbac_user_mappings WHERE guild_id = ? AND user_id = ?;",
            (guild_id, user_id),
        )
        for row in user_rows:
            lvl_str = row["permission_level"]
            score = PERMISSION_HIERARCHY.get(lvl_str, 0)
            if score > highest_score:
                highest_score = score
                best_level = PermissionLevel(lvl_str)

        # Check role permission mappings in SQLite
        member_role_ids = [int(r.id) for r in getattr(member, "roles", [])]
        if member_role_ids:
            placeholders = ",".join("?" for _ in member_role_ids)
            role_rows = await self.db.fetch_all(
                f"SELECT permission_level FROM rbac_role_mappings WHERE guild_id = ? AND role_id IN ({placeholders});",
                [guild_id, *member_role_ids],
            )
            for row in role_rows:
                lvl_str = row["permission_level"]
                score = PERMISSION_HIERARCHY.get(lvl_str, 0)
                if score > highest_score:
                    highest_score = score
                    best_level = PermissionLevel(lvl_str)

        # Native Discord Moderator fallback if no explicit higher mapping
        if highest_score < PERMISSION_HIERARCHY[PermissionLevel.MODERATOR.value] and guild_perms:
            if (
                getattr(guild_perms, "manage_guild", False)
                or getattr(guild_perms, "ban_members", False)
                or getattr(guild_perms, "kick_members", False)
                or getattr(guild_perms, "moderate_members", False)
            ):
                best_level = PermissionLevel.MODERATOR

        return best_level

    async def authorize_interaction(
        self,
        interaction: discord.Interaction,
        command_name: str,
        module_name: str,
        default_level: PermissionLevel = PermissionLevel.EVERYONE,
    ) -> Tuple[bool, str]:
        """
        Validate whether `interaction.user` is authorized to run `command_name` in `module_name`.
        Returns `(is_authorized, reason_message)`.
        """
        guild = interaction.guild
        user = interaction.user
        if guild is None:
            if int(getattr(user, "id", 0)) == self.bot_owner_id:
                return True, "Authorized as Bot Owner."
            return False, "This command can only be executed inside a Discord server."

        guild_id = int(guild.id)
        user_id = int(user.id)
        effective_level = await self.get_member_effective_level(guild, user)
        effective_score = PERMISSION_HIERARCHY[effective_level.value]

        # Bot Owner and Server Owner always pass
        if effective_level in (PermissionLevel.BOT_OWNER, PermissionLevel.SERVER_OWNER):
            return True, f"Authorized as {effective_level.value}."

        # Check if module is disabled in guild_configs or rbac_module_rules
        mod_rule = await self.db.fetch_one(
            "SELECT * FROM rbac_module_rules WHERE guild_id = ? AND module_name = ?;",
            (guild_id, module_name),
        )
        if mod_rule and not bool(mod_rule["enabled"]) and effective_score < PERMISSION_HIERARCHY[PermissionLevel.ADMIN.value]:
            return False, f"The `{module_name}` module is currently disabled by server administrators."

        # Check command-specific rule override
        cmd_rule = await self.db.fetch_one(
            "SELECT * FROM rbac_command_rules WHERE guild_id = ? AND command_name = ?;",
            (guild_id, command_name),
        )
        member_role_ids = {int(r.id) for r in getattr(user, "roles", [])}

        if cmd_rule:
            if not bool(cmd_rule["enabled"]) and effective_score < PERMISSION_HIERARCHY[PermissionLevel.ADMIN.value]:
                return False, f"The command `/{command_name}` is currently disabled in this server."

            allowed_users = set(json.loads(cmd_rule.get("allowed_user_ids_json") or "[]"))
            if user_id in allowed_users:
                return True, "Authorized via explicit command user allowlist."

            allowed_roles = set(json.loads(cmd_rule.get("allowed_role_ids_json") or "[]"))
            if allowed_roles and (member_role_ids & allowed_roles):
                return True, "Authorized via explicit command role allowlist."

            req_level_str = cmd_rule.get("required_level") or default_level.value
        elif mod_rule:
            allowed_roles = set(json.loads(mod_rule.get("allowed_role_ids_json") or "[]"))
            if allowed_roles and (member_role_ids & allowed_roles):
                return True, "Authorized via explicit module role allowlist."
            req_level_str = mod_rule.get("required_level") or default_level.value
        else:
            req_level_str = default_level.value

        required_score = PERMISSION_HIERARCHY.get(req_level_str, 0)
        if effective_score >= required_score:
            return True, f"Authorized ({effective_level.value} >= {req_level_str})."

        return (
            False,
            f"Insufficient RBAC Permissions: `/{command_name}` requires **{req_level_str}** "
            f"(your effective level is **{effective_level.value}**).",
        )

    async def validate_permission_mutation(
        self,
        guild: Any,
        actor: Any,
        target_level: str,
        target_user_id: Optional[int] = None,
    ) -> None:
        """
        Enforce anti-escalation rules before modifying any RBAC role or user mapping:
        - Cannot grant `bot_owner` or `server_owner`.
        - Never allow a user to grant themselves `administrator` permissions.
        - Cannot modify permissions for the Bot Owner or Server Owner.
        - Actor cannot assign a permission level greater than or equal to their own unless Server Owner / Bot Owner.
        """
        if target_level not in PERMISSION_HIERARCHY:
            raise ValueError(f"Invalid permission level: {target_level}")

        if target_level in (PermissionLevel.BOT_OWNER.value, PermissionLevel.SERVER_OWNER.value):
            raise PrivilegeEscalationError("Cannot assign reserved owner permission levels via RBAC.")

        actor_id = int(getattr(actor, "id", 0))
        if target_user_id is not None:
            if int(target_user_id) == actor_id and target_level == PermissionLevel.ADMIN.value:
                raise PrivilegeEscalationError(
                    "Security Policy Violation: You cannot grant yourself Administrator permissions."
                )
            if int(target_user_id) == self.bot_owner_id:
                raise PrivilegeEscalationError("Cannot modify permissions of the Bot Owner.")
            if guild is not None and int(target_user_id) == int(getattr(guild, "owner_id", 0)):
                raise PrivilegeEscalationError("Cannot modify permissions of the Server Owner.")

        actor_level = await self.get_member_effective_level(guild, actor)
        actor_score = PERMISSION_HIERARCHY[actor_level.value]
        target_score = PERMISSION_HIERARCHY[target_level]

        if actor_level not in (PermissionLevel.BOT_OWNER, PermissionLevel.SERVER_OWNER):
            if target_score >= actor_score:
                raise PrivilegeEscalationError(
                    f"Privilege Escalation Blocked: Your level ({actor_level.value}) cannot grant or modify "
                    f"equal/higher level ({target_level})."
                )

    async def add_role_permission(self, guild: Any, actor: Any, role_id: int, level: str) -> None:
        await self.validate_permission_mutation(guild, actor, level)
        await self.db.execute(
            """
            INSERT INTO rbac_role_mappings (guild_id, role_id, permission_level)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, role_id, permission_level) DO NOTHING;
            """,
            (int(guild.id), int(role_id), level),
        )

    async def remove_role_permission(self, guild: Any, actor: Any, role_id: int, level: str) -> None:
        await self.validate_permission_mutation(guild, actor, level)
        await self.db.execute(
            "DELETE FROM rbac_role_mappings WHERE guild_id = ? AND role_id = ? AND permission_level = ?;",
            (int(guild.id), int(role_id), level),
        )

    async def add_user_permission(self, guild: Any, actor: Any, user_id: int, level: str) -> None:
        await self.validate_permission_mutation(guild, actor, level, target_user_id=user_id)
        await self.db.execute(
            """
            INSERT INTO rbac_user_mappings (guild_id, user_id, permission_level)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id, permission_level) DO NOTHING;
            """,
            (int(guild.id), int(user_id), level),
        )

    async def remove_user_permission(self, guild: Any, actor: Any, user_id: int, level: str) -> None:
        await self.validate_permission_mutation(guild, actor, level, target_user_id=user_id)
        await self.db.execute(
            "DELETE FROM rbac_user_mappings WHERE guild_id = ? AND user_id = ? AND permission_level = ?;",
            (int(guild.id), int(user_id), level),
        )

    async def set_command_rule(
        self,
        guild: Any,
        actor: Any,
        command_name: str,
        module_name: str,
        required_level: str,
        allowed_role_ids: Optional[List[int]] = None,
        allowed_user_ids: Optional[List[int]] = None,
        enabled: bool = True,
    ) -> None:
        await self.validate_permission_mutation(guild, actor, required_level)
        clean_cmd = command_name.strip().lstrip("/")
        await self.db.execute(
            """
            INSERT INTO rbac_command_rules (
                guild_id, command_name, module_name, required_level,
                allowed_role_ids_json, allowed_user_ids_json, enabled, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(guild_id, command_name) DO UPDATE SET
                module_name = excluded.module_name,
                required_level = excluded.required_level,
                allowed_role_ids_json = excluded.allowed_role_ids_json,
                allowed_user_ids_json = excluded.allowed_user_ids_json,
                enabled = excluded.enabled,
                updated_at = datetime('now');
            """,
            (
                int(guild.id),
                clean_cmd,
                module_name,
                required_level,
                json.dumps(allowed_role_ids or []),
                json.dumps(allowed_user_ids or []),
                1 if enabled else 0,
            ),
        )

    async def set_module_rule(
        self,
        guild: Any,
        actor: Any,
        module_name: str,
        required_level: str,
        allowed_role_ids: Optional[List[int]] = None,
        enabled: bool = True,
    ) -> None:
        await self.validate_permission_mutation(guild, actor, required_level)
        await self.db.execute(
            """
            INSERT INTO rbac_module_rules (
                guild_id, module_name, required_level, allowed_role_ids_json, enabled, updated_at
            ) VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(guild_id, module_name) DO UPDATE SET
                required_level = excluded.required_level,
                allowed_role_ids_json = excluded.allowed_role_ids_json,
                enabled = excluded.enabled,
                updated_at = datetime('now');
            """,
            (
                int(guild.id),
                module_name,
                required_level,
                json.dumps(allowed_role_ids or []),
                1 if enabled else 0,
            ),
        )

    async def reset_guild_permissions(self, guild: Any, actor: Any) -> None:
        actor_level = await self.get_member_effective_level(guild, actor)
        if actor_level not in (PermissionLevel.BOT_OWNER, PermissionLevel.SERVER_OWNER, PermissionLevel.ADMIN):
            raise PrivilegeEscalationError("Only Server Owners or Administrators can reset RBAC rules.")
        gid = int(guild.id)
        await self.db.execute_many(
            [
                ("DELETE FROM rbac_role_mappings WHERE guild_id = ?;", (gid,)),
                ("DELETE FROM rbac_user_mappings WHERE guild_id = ?;", (gid,)),
                ("DELETE FROM rbac_command_rules WHERE guild_id = ?;", (gid,)),
                ("DELETE FROM rbac_module_rules WHERE guild_id = ?;", (gid,)),
            ]
        )

    async def get_guild_permission_summary(self, guild_id: int) -> Dict[str, Any]:
        roles = await self.db.fetch_all("SELECT * FROM rbac_role_mappings WHERE guild_id = ?;", (guild_id,))
        users = await self.db.fetch_all("SELECT * FROM rbac_user_mappings WHERE guild_id = ?;", (guild_id,))
        cmds = await self.db.fetch_all("SELECT * FROM rbac_command_rules WHERE guild_id = ?;", (guild_id,))
        mods = await self.db.fetch_all("SELECT * FROM rbac_module_rules WHERE guild_id = ?;", (guild_id,))
        return {
            "role_mappings": roles,
            "user_mappings": users,
            "command_rules": cmds,
            "module_rules": mods,
        }
