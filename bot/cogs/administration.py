"""
Server Administration & Diagnostics Cog for Cosmic ki baddie.

Implements all 11 required administration slash commands:
- `/serverinfo`
- `/userinfo`
- `/roleinfo`
- `/channelinfo`
- `/botinfo`
- `/settings`
- `/dashboard`
- `/backup`
- `/restore`
- `/logs`
- `/prefix`
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional

from bot.core.discord_compat import app_commands, commands, discord
from bot.database.models import PermissionLevel
from bot.ui.dashboard import SetupDashboardView
from bot.utils.checks import require_permission_level

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot


class AdministrationCog(commands.Cog):
    """Server Administration, Backups, Diagnostics, and Info Utilities."""

    def __init__(self, bot: "CosmicBot") -> None:
        self.bot = bot

    @app_commands.command(name="serverinfo", description="Display comprehensive information and statistics about this server.")
    async def serverinfo_command(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        embed = discord.Embed(title=f"Server Information — {guild.name}", color=discord.Color.blurple())
        embed.add_field(name="Server ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="Owner", value=f"<@{guild.owner_id}> (`{guild.owner_id}`)", inline=True)
        embed.add_field(name="Members", value=str(getattr(guild, "member_count", len(getattr(guild, "members", [])))), inline=True)
        embed.add_field(name="Text Channels", value=str(len(getattr(guild, "text_channels", []))), inline=True)
        embed.add_field(name="Voice Channels", value=str(len(getattr(guild, "voice_channels", []))), inline=True)
        embed.add_field(name="Roles", value=str(len(getattr(guild, "roles", []))), inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Inspect roles, effective RBAC permission level, and profile info for a member.")
    @app_commands.describe(member="Member to inspect (defaults to yourself)")
    async def userinfo_command(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        if interaction.guild is None:
            return
        target = member or interaction.user
        eff_level = await self.bot.permission_service.get_member_effective_level(interaction.guild, target)
        roles = [r.mention for r in getattr(target, "roles", []) if getattr(r, "name", "") != "@everyone"]
        embed = discord.Embed(title=f"Member Profile — {target.name}", color=discord.Color.blurple())
        embed.add_field(name="User ID", value=f"`{target.id}`", inline=True)
        embed.add_field(name="Top Role", value=getattr(getattr(target, "top_role", None), "mention", "@everyone"), inline=True)
        embed.add_field(name="RBAC Level", value=f"`{eff_level.value}`", inline=True)
        embed.add_field(name=f"Roles ({len(roles)})", value=", ".join(roles[:15]) or "None", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roleinfo", description="Display hierarchy position, color, and permissions for a Discord role.")
    @app_commands.describe(role="Role to inspect")
    async def roleinfo_command(self, interaction: discord.Interaction, role: discord.Role) -> None:
        embed = discord.Embed(title=f"Role Information — {role.name}", color=role.color)
        embed.add_field(name="Role ID", value=f"`{role.id}`", inline=True)
        embed.add_field(name="Hierarchy Position", value=str(role.position), inline=True)
        embed.add_field(name="Administrator", value=str(bool(getattr(role.permissions, "administrator", False))), inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="channelinfo", description="Display configuration and slowmode details for a channel.")
    @app_commands.describe(channel="Channel to inspect (defaults to current)")
    async def channelinfo_command(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        target = channel or interaction.channel
        embed = discord.Embed(title=f"Channel Info — #{getattr(target, 'name', 'channel')}", color=discord.Color.blurple())
        embed.add_field(name="Channel ID", value=f"`{target.id}`", inline=True)
        embed.add_field(name="Slowmode", value=f"`{getattr(target, 'slowmode_delay', 0)}s`", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="botinfo", description="Run the complete Cosmic ki baddie Command & Database Health Check.")
    async def botinfo_command(self, interaction: discord.Interaction) -> None:
        report = await self.bot.health_monitor.generate_full_diagnostic_report(guild=interaction.guild)
        cmd_meta = report["commands"]
        db_meta = report["database"]
        ext_meta = report["extensions"]

        embed = discord.Embed(
            title="Cosmic ki baddie (Aurora) — System & Command Health Diagnostic",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Command Registry",
            value=(
                f"Implemented: **{cmd_meta['total_implemented']}**\n"
                f"Registered: **{cmd_meta['total_registered']}**\n"
                f"Synchronized: **{cmd_meta['total_synchronized']}**\n"
                f"Failed: **{len(cmd_meta['failed_commands'])}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Extensions & Cogs",
            value=(
                f"Loaded Cogs: **{ext_meta['total_loaded']}**\n"
                f"Failed Cogs: **{ext_meta['total_failed']}**\n"
                f"Persistent Views: **{report['voice_and_media']['persistent_views_registered']}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="SQLite Database",
            value=(
                f"Connected: **{db_meta.get('connected')}**\n"
                f"Driver: `{db_meta.get('driver')}`\n"
                f"Migrations: `v{db_meta.get('schema_version')}/{db_meta.get('total_migrations')}`"
            ),
            inline=True,
        )
        missing_perms = report["permissions"]["missing_guild_permissions"]
        embed.add_field(
            name="Discord Guild Permissions",
            value="All required permissions granted" if not missing_perms else f"Missing: {', '.join(f'`{p}`' for p in missing_perms)}",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="settings", description="View or toggle server module states and configuration settings.")
    @app_commands.describe(module_to_toggle="Optional module name to enable/disable")
    @require_permission_level(PermissionLevel.ADMIN, module_name="administration")
    async def settings_command(
        self,
        interaction: discord.Interaction,
        module_to_toggle: Optional[str] = None,
    ) -> None:
        if interaction.guild is None:
            return
        guild_id = int(interaction.guild.id)
        cfg = await self.bot.logging_service.ensure_guild_config(guild_id)
        modules = json.loads(cfg.get("enabled_modules_json") or "{}")

        if module_to_toggle and module_to_toggle.strip():
            key = module_to_toggle.strip().lower()
            if key in modules:
                modules[key] = not modules[key]
                cfg = await self.bot.logging_service.update_guild_config(
                    guild_id,
                    enabled_modules_json=json.dumps(modules),
                )

        embed = discord.Embed(title=f"Server Settings — {interaction.guild.name}", color=discord.Color.blurple())
        embed.add_field(name="Command Prefix", value=f"`{cfg.get('prefix', '!')}`", inline=True)
        embed.add_field(name="Snipe Retention Limit", value=str(cfg.get("snipe_limit", 25)), inline=True)
        mod_lines = [f"• `{k}`: **{'Enabled' if v else 'Disabled'}**" for k, v in modules.items()]
        embed.add_field(name="Modules", value="\n".join(mod_lines), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="dashboard", description="Open the interactive 14-page Server Administration Dashboard.")
    @require_permission_level(PermissionLevel.ADMIN, module_name="administration")
    async def dashboard_command(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        view = SetupDashboardView(self.bot, author_id=int(interaction.user.id), initial_page="overview")
        embed = await view.build_page_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="backup", description="Create a complete SQLite configuration snapshot backup for this server.")
    @app_commands.describe(label="Descriptive label for this backup")
    @require_permission_level(PermissionLevel.ADMIN, module_name="administration")
    async def backup_command(
        self,
        interaction: discord.Interaction,
        label: str = "Manual Admin Backup",
    ) -> None:
        if interaction.guild is None:
            return
        res = await self.bot.db.create_guild_backup(
            guild_id=int(interaction.guild.id),
            created_by_id=int(interaction.user.id),
            label=label,
        )
        await interaction.response.send_message(
            f"Created server configuration backup `#{res['backup_id']}` (`{label}`). Use `/restore {res['backup_id']}` to restore.",
            ephemeral=True,
        )

    @app_commands.command(name="restore", description="Restore a previously saved server configuration backup by Backup ID.")
    @app_commands.describe(backup_id="Backup ID to restore")
    @require_permission_level(PermissionLevel.ADMIN, module_name="administration")
    async def restore_command(self, interaction: discord.Interaction, backup_id: int) -> None:
        if interaction.guild is None:
            return
        ok = await self.bot.db.restore_guild_backup(int(interaction.guild.id), int(backup_id))
        if not ok:
            await interaction.response.send_message(f"Backup `#{backup_id}` not found for this server.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Successfully restored server configuration from Backup `#{backup_id}`.",
            ephemeral=True,
        )

    @app_commands.command(name="logs", description="Configure the Moderation, Server Audit, and Ticket Transcript log channels.")
    @app_commands.describe(
        mod_log_channel="Channel for moderation case embeds",
        server_log_channel="Channel for general server audit logs",
        transcript_channel="Default channel for closed ticket transcripts",
    )
    @require_permission_level(PermissionLevel.ADMIN, module_name="administration")
    async def logs_command(
        self,
        interaction: discord.Interaction,
        mod_log_channel: Optional[discord.TextChannel] = None,
        server_log_channel: Optional[discord.TextChannel] = None,
        transcript_channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if interaction.guild is None:
            return
        updates = {}
        if mod_log_channel is not None:
            updates["mod_log_channel_id"] = int(mod_log_channel.id)
        if server_log_channel is not None:
            updates["server_log_channel_id"] = int(server_log_channel.id)
        if transcript_channel is not None:
            updates["transcript_channel_id"] = int(transcript_channel.id)

        cfg = await self.bot.logging_service.update_guild_config(int(interaction.guild.id), **updates)
        embed = discord.Embed(title="Updated Server Logging Channels", color=discord.Color.green())
        embed.add_field(
            name="Moderation Log",
            value=f"<#{cfg['mod_log_channel_id']}>" if cfg.get("mod_log_channel_id") else "`Not Set`",
            inline=True,
        )
        embed.add_field(
            name="Server Audit Log",
            value=f"<#{cfg['server_log_channel_id']}>" if cfg.get("server_log_channel_id") else "`Not Set`",
            inline=True,
        )
        embed.add_field(
            name="Ticket Transcripts",
            value=f"<#{cfg['transcript_channel_id']}>" if cfg.get("transcript_channel_id") else "`Not Set`",
            inline=True,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="prefix", description="Change the fallback text command prefix for this server.")
    @app_commands.describe(new_prefix="New prefix (1-5 characters, e.g. ! or ?)")
    @require_permission_level(PermissionLevel.ADMIN, module_name="administration")
    async def prefix_command(self, interaction: discord.Interaction, new_prefix: str) -> None:
        if interaction.guild is None:
            return
        clean = new_prefix.strip()[:5] or "!"
        await self.bot.logging_service.update_guild_config(int(interaction.guild.id), prefix=clean)
        await interaction.response.send_message(f"Updated server command prefix to `{clean}`.", ephemeral=True)


async def setup(bot: "CosmicBot") -> None:
    await bot.add_cog(AdministrationCog(bot))
