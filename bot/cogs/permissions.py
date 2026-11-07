"""
Advanced RBAC & Permission Management Cog for Cosmic ki baddie.

Implements all 10 required permission commands with nested subgroups (`role`, `user`):
- `/permissions` ( existed as `/permissions view` and `/permissions setup` + interactive dashboard)
- `/permissions setup`
- `/permissions role add`
- `/permissions role remove`
- `/permissions user add`
- `/permissions user remove`
- `/permissions command`
- `/permissions module`
- `/permissions reset`
- `/permissions view`
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from bot.core.discord_compat import app_commands, commands, discord
from bot.database.models import PERMISSION_HIERARCHY, PermissionLevel
from bot.ui.confirmations import ConfirmationView
from bot.utils.checks import require_permission_level

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot


class PermissionsInteractiveView(discord.ui.View):
    """Interactive Permission Management Dashboard View showing Module, Command, Required Level, and Roles."""

    def __init__(self, bot: "CosmicBot", author_id: int) -> None:
        super().__init__(timeout=300.0)
        self.bot = bot
        self.author_id = int(author_id)
        self.selected_module = "moderation"

        mod_options = [
            discord.SelectOption(label=m.replace("_", " ").title(), value=m, default=(m == self.selected_module))
            for m in [
                "moderation",
                "tickets",
                "permissions",
                "jtc",
                "activity_roles",
                "reaction_roles",
                "music",
                "ai_assistant",
                "auto_responder",
                "embeds",
                "administration",
            ]
        ]
        self.mod_select = discord.ui.Select(
            placeholder="Select Module to Inspect / Modify...",
            options=mod_options,
            custom_id="cosmic:perm_ui:module_select",
            row=0,
        )
        self.mod_select.callback = self._on_select_module
        self.add_item(self.mod_select)

        lvl_options = [
            discord.SelectOption(label=f"Require {lvl.value}", value=lvl.value)
            for lvl in [
                PermissionLevel.EVERYONE,
                PermissionLevel.DJ,
                PermissionLevel.TICKET_STAFF,
                PermissionLevel.SUPPORT,
                PermissionLevel.MODERATOR,
                PermissionLevel.ADMIN,
            ]
        ]
        self.lvl_select = discord.ui.Select(
            placeholder="Set Required Permission Level for Module...",
            options=lvl_options,
            custom_id="cosmic:perm_ui:level_select",
            row=1,
        )
        self.lvl_select.callback = self._on_select_level
        self.add_item(self.lvl_select)

    async def _on_select_module(self, interaction: discord.Interaction) -> None:
        if int(interaction.user.id) != self.author_id:
            await interaction.response.send_message("Only the administrator who opened this panel can use it.", ephemeral=True)
            return
        if self.mod_select.values:
            self.selected_module = self.mod_select.values[0]
        embed = await self.build_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_select_level(self, interaction: discord.Interaction) -> None:
        if int(interaction.user.id) != self.author_id or interaction.guild is None:
            return
        chosen_level = self.lvl_select.values[0] if self.lvl_select.values else PermissionLevel.MODERATOR.value
        await self.bot.permission_service.set_module_rule(
            guild=interaction.guild,
            actor=interaction.user,
            module_name=self.selected_module,
            required_level=chosen_level,
            enabled=True,
        )
        embed = await self.build_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    async def build_embed(self, guild: discord.Guild) -> discord.Embed:
        summary = await self.bot.permission_service.get_guild_permission_summary(int(guild.id))
        embed = discord.Embed(
            title=f"RBAC Permission Matrix — {guild.name}",
            description=(
                f"Currently inspecting module: **{self.selected_module}**\n"
                "All permissions are enforced server-side with hierarchy and anti-escalation protection."
            ),
            color=discord.Color.blurple(),
        )
        role_lines = [
            f"<@&{r['role_id']}> → `{r['permission_level']}`" for r in summary["role_mappings"][:12]
        ] or ["No custom role mappings configured yet."]
        user_lines = [
            f"<@{u['user_id']}> → `{u['permission_level']}`" for u in summary["user_mappings"][:12]
        ] or ["No individual user grants configured."]
        cmd_lines = [
            f"`/{c['command_name']}` ({c['module_name']}) → `{c['required_level']}` [{'Enabled' if c['enabled'] else 'Disabled'}]"
            for c in summary["command_rules"][:12]
        ] or ["Using default module RBAC rules."]

        embed.add_field(name="Authorized Roles", value="\n".join(role_lines), inline=True)
        embed.add_field(name="Authorized Users", value="\n".join(user_lines), inline=True)
        embed.add_field(name="Command Overrides", value="\n".join(cmd_lines), inline=False)
        return embed


class PermissionsCog(commands.Cog):
    """Centralized Role-Based Access Control (RBAC) Slash Command Suite."""

    permissions_group = app_commands.Group(
        name="permissions",
        description="Configure Role-Based Access Control (RBAC) for roles, users, commands, and modules.",
    )
    role_subgroup = app_commands.Group(
        name="role",
        description="Manage RBAC permission levels assigned to Discord roles.",
        parent=permissions_group,
    )
    user_subgroup = app_commands.Group(
        name="user",
        description="Manage RBAC permission levels assigned to individual Discord users.",
        parent=permissions_group,
    )

    def __init__(self, bot: "CosmicBot") -> None:
        self.bot = bot

    @permissions_group.command(name="setup", description="Open the interactive RBAC Permission Management Dashboard.")
    @require_permission_level(PermissionLevel.ADMIN, module_name="permissions")
    async def permissions_setup(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        view = PermissionsInteractiveView(self.bot, author_id=int(interaction.user.id))
        embed = await view.build_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @permissions_group.command(name="view", description="View all active RBAC role, user, command, and module permissions.")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="permissions")
    async def permissions_view(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        view = PermissionsInteractiveView(self.bot, author_id=int(interaction.user.id))
        embed = await view.build_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @role_subgroup.command(name="add", description="Grant an RBAC permission level to a Discord role.")
    @app_commands.describe(
        role="The Discord role to authorize",
        level="Permission level (music_dj, ticket_staff, support_team, moderator, administrator)",
    )
    @require_permission_level(PermissionLevel.ADMIN, module_name="permissions")
    async def role_add(self, interaction: discord.Interaction, role: discord.Role, level: str) -> None:
        if interaction.guild is None:
            return
        clean_level = level.strip().lower()
        if clean_level not in PERMISSION_HIERARCHY:
            await interaction.response.send_message(
                f"Invalid level `{clean_level}`. Valid levels: `music_dj`, `ticket_staff`, `support_team`, `moderator`, `administrator`.",
                ephemeral=True,
            )
            return
        await self.bot.permission_service.add_role_permission(
            guild=interaction.guild,
            actor=interaction.user,
            role_id=int(role.id),
            level=clean_level,
        )
        await interaction.response.send_message(
            f"Granted RBAC level **{clean_level}** to role {role.mention}.",
            ephemeral=True,
        )

    @role_subgroup.command(name="remove", description="Revoke an RBAC permission level from a Discord role.")
    @app_commands.describe(role="The Discord role to update", level="Permission level to remove")
    @require_permission_level(PermissionLevel.ADMIN, module_name="permissions")
    async def role_remove(self, interaction: discord.Interaction, role: discord.Role, level: str) -> None:
        if interaction.guild is None:
            return
        clean_level = level.strip().lower()
        await self.bot.permission_service.remove_role_permission(
            guild=interaction.guild,
            actor=interaction.user,
            role_id=int(role.id),
            level=clean_level,
        )
        await interaction.response.send_message(
            f"Removed RBAC level **{clean_level}** from role {role.mention}.",
            ephemeral=True,
        )

    @user_subgroup.command(name="add", description="Grant an RBAC permission level to a specific user.")
    @app_commands.describe(user="The Discord member to authorize", level="Permission level to grant")
    @require_permission_level(PermissionLevel.ADMIN, module_name="permissions")
    async def user_add(self, interaction: discord.Interaction, user: discord.Member, level: str) -> None:
        if interaction.guild is None:
            return
        clean_level = level.strip().lower()
        await self.bot.permission_service.add_user_permission(
            guild=interaction.guild,
            actor=interaction.user,
            user_id=int(user.id),
            level=clean_level,
        )
        await interaction.response.send_message(
            f"Granted RBAC level **{clean_level}** to {user.mention}.",
            ephemeral=True,
        )

    @user_subgroup.command(name="remove", description="Revoke an RBAC permission level from a specific user.")
    @app_commands.describe(user="The Discord member to update", level="Permission level to revoke")
    @require_permission_level(PermissionLevel.ADMIN, module_name="permissions")
    async def user_remove(self, interaction: discord.Interaction, user: discord.Member, level: str) -> None:
        if interaction.guild is None:
            return
        clean_level = level.strip().lower()
        await self.bot.permission_service.remove_user_permission(
            guild=interaction.guild,
            actor=interaction.user,
            user_id=int(user.id),
            level=clean_level,
        )
        await interaction.response.send_message(
            f"Revoked RBAC level **{clean_level}** from {user.mention}.",
            ephemeral=True,
        )

    @permissions_group.command(name="command", description="Configure required RBAC permission level for a specific slash command.")
    @app_commands.describe(
        command_name="Qualified slash command name (e.g. ban, jticket close, play)",
        module_name="Module name (e.g. moderation, tickets, music)",
        required_level="Required permission level",
        enabled="Whether this command is enabled in this server",
    )
    @require_permission_level(PermissionLevel.ADMIN, module_name="permissions")
    async def permissions_command(
        self,
        interaction: discord.Interaction,
        command_name: str,
        module_name: str,
        required_level: str,
        enabled: bool = True,
    ) -> None:
        if interaction.guild is None:
            return
        await self.bot.permission_service.set_command_rule(
            guild=interaction.guild,
            actor=interaction.user,
            command_name=command_name,
            module_name=module_name,
            required_level=required_level.strip().lower(),
            enabled=enabled,
        )
        await interaction.response.send_message(
            f"Updated RBAC rule for `/{command_name.lstrip('/')}` → requires **{required_level}** (`enabled={enabled}`).",
            ephemeral=True,
        )

    @permissions_group.command(name="module", description="Configure required RBAC permission level or status for an entire module.")
    @app_commands.describe(
        module_name="Module name (e.g. moderation, tickets, music, jtc)",
        required_level="Minimum permission level required for module commands",
        enabled="Whether this module is enabled",
    )
    @require_permission_level(PermissionLevel.ADMIN, module_name="permissions")
    async def permissions_module(
        self,
        interaction: discord.Interaction,
        module_name: str,
        required_level: str,
        enabled: bool = True,
    ) -> None:
        if interaction.guild is None:
            return
        await self.bot.permission_service.set_module_rule(
            guild=interaction.guild,
            actor=interaction.user,
            module_name=module_name.strip().lower(),
            required_level=required_level.strip().lower(),
            enabled=enabled,
        )
        await interaction.response.send_message(
            f"Updated module `{module_name}` → minimum level **{required_level}** (`enabled={enabled}`).",
            ephemeral=True,
        )

    @permissions_group.command(name="reset", description="Reset all custom RBAC role, user, command, and module rules to default.")
    @require_permission_level(PermissionLevel.ADMIN, module_name="permissions")
    async def permissions_reset(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return

        async def _confirm_reset(confirm_inter: discord.Interaction) -> None:
            await self.bot.permission_service.reset_guild_permissions(interaction.guild, interaction.user)
            embed = discord.Embed(
                title="RBAC Permissions Reset",
                description="All custom role, user, command, and module permission overrides have been reset to defaults.",
                color=discord.Color.green(),
            )
            await confirm_inter.response.edit_message(embed=embed, view=None)

        view = ConfirmationView(author_id=int(interaction.user.id), on_confirm=_confirm_reset, confirm_label="Reset All RBAC Rules")
        prompt = discord.Embed(
            title="Confirm RBAC Reset",
            description="Are you sure you want to wipe all custom RBAC mappings for this server?",
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=prompt, view=view, ephemeral=True)


async def setup(bot: "CosmicBot") -> None:
    await bot.add_cog(PermissionsCog(bot))
