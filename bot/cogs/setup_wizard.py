"""
Setup Wizard & Interactive Help Cog for Cosmic ki baddie.
Implements:
- `/setup` — Launches the 14-page interactive server management dashboard
- `/help` — Interactive categorized slash command explorer & live command health check
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

from bot.core.discord_compat import app_commands, commands, discord
from bot.database.models import PermissionLevel
from bot.ui.dashboard import SetupDashboardView
from bot.ui.pagination import PaginatedEmbedView
from bot.utils.checks import require_permission_level

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot


class SetupWizardCog(commands.Cog):
    """Provides `/setup` and `/help` interactive experiences."""

    def __init__(self, bot: "CosmicBot") -> None:
        self.bot = bot

    @app_commands.command(
        name="setup",
        description="Launch the 14-page interactive Cosmic ki baddie server configuration dashboard.",
    )
    @app_commands.describe(page="Optional starting dashboard page (e.g. overview, tickets, permissions, moderation)")
    @require_permission_level(PermissionLevel.ADMIN, module_name="administration")
    async def setup_command(self, interaction: discord.Interaction, page: Optional[str] = "overview") -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Run `/setup` inside a Discord server.", ephemeral=True)
            return

        target_page = (page or "overview").strip().lower()
        view = SetupDashboardView(self.bot, author_id=int(interaction.user.id), initial_page=target_page)
        embed = await view.build_page_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(
        name="help",
        description="Interactive command directory and real-time command registry health check.",
    )
    @app_commands.describe(module="Filter commands by module or Cog name")
    async def help_command(self, interaction: discord.Interaction, module: Optional[str] = None) -> None:
        report = self.bot.command_sync.audit_registered_commands()
        grouped: Dict[str, List[Dict[str, str]]] = {}
        for cmd in report.registered_commands:
            cog_label = cmd["cog"].replace("Cog", "")
            if module and module.lower() not in cog_label.lower() and module.lower() not in cmd["qualified_name"].lower():
                continue
            grouped.setdefault(cog_label, []).append(cmd)

        pages: List[discord.Embed] = []
        overview_embed = discord.Embed(
            title="Cosmic ki baddie (Aurora) — Interactive Command Directory",
            description=(
                "Use the pagination buttons below to browse all registered Slash Commands by module.\n"
                "Administrators can configure every module inside Discord using `/setup` or `/dashboard`."
            ),
            color=discord.Color.blurple(),
        )
        overview_embed.add_field(
            name="Command Registry Health",
            value=(
                f"Implemented: **{report.total_implemented}**\n"
                f"Registered: **{report.total_registered}**\n"
                f"Failed / Conflicts: **{len(report.failed_commands)}**"
            ),
            inline=True,
        )
        overview_embed.add_field(
            name="Core Modules (12 Cogs)",
            value=", ".join(f"`{k}` ({len(v)})" for k, v in sorted(grouped.items())) or "No matching commands",
            inline=False,
        )
        pages.append(overview_embed)

        for mod_name, cmds in sorted(grouped.items()):
            mod_embed = discord.Embed(
                title=f"Module: {mod_name} ({len(cmds)} Commands)",
                color=discord.Color.blurple(),
            )
            lines = [f"• `{c['qualified_name']}` — {c['description']}" for c in cmds[:20]]
            mod_embed.description = "\n".join(lines)
            pages.append(mod_embed)

        paginator = PaginatedEmbedView(pages=pages, author_id=int(interaction.user.id))
        await interaction.response.send_message(embed=paginator.current_embed, view=paginator, ephemeral=True)


async def setup(bot: "CosmicBot") -> None:
    await bot.add_cog(SetupWizardCog(bot))
