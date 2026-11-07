"""
Reaction Role System Cog (`/reactionrole`) for Cosmic ki baddie.

Implements all 7 required `/reactionrole` slash commands:
- `/reactionrole setup`
- `/reactionrole create`
- `/reactionrole edit`
- `/reactionrole delete`
- `/reactionrole list`
- `/reactionrole add`
- `/reactionrole remove`

Features:
- Button roles, Dropdown roles, and Emoji Reaction roles
- Exclusive role groups & max roles per user
- Prevents assigning roles above the bot's highest role (`validate_assignable_role`)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional

from bot.core.discord_compat import app_commands, commands, discord
from bot.database.models import PermissionLevel
from bot.ui.dashboard import SetupDashboardView
from bot.ui.persistent_views import PersistentReactionRoleView
from bot.utils.checks import require_permission_level
from bot.utils.validators import validate_assignable_role

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot


class ReactionRolesCog(commands.Cog):
    """Self-assignable Reaction Role panels (Buttons, Dropdowns, Emoji Reactions)."""

    reactionrole_group = app_commands.Group(
        name="reactionrole",
        description="Create and manage persistent self-assignable role panels.",
    )

    def __init__(self, bot: "CosmicBot") -> None:
        self.bot = bot

    @reactionrole_group.command(name="setup", description="Launch the Reaction Roles interactive configuration dashboard.")
    @require_permission_level(PermissionLevel.ADMIN, module_name="reaction_roles")
    async def rr_setup(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        view = SetupDashboardView(self.bot, author_id=int(interaction.user.id), initial_page="reaction_roles")
        embed = await view.build_page_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @reactionrole_group.command(name="create", description="Create a new Reaction Role panel in the specified channel.")
    @app_commands.describe(
        title="Panel embed title",
        description="Panel embed description",
        mode="Panel interaction style: buttons, dropdown, or reactions",
        exclusive="If True, users can only hold one role from this panel at a time",
        max_roles="Maximum roles a user can select from this panel (0 = unlimited)",
    )
    @require_permission_level(PermissionLevel.ADMIN, module_name="reaction_roles")
    async def rr_create(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str = "Select your roles below:",
        mode: str = "buttons",
        exclusive: bool = False,
        max_roles: int = 0,
    ) -> None:
        if interaction.guild is None:
            return
        clean_mode = mode.strip().lower()
        if clean_mode not in ("buttons", "dropdown", "reactions"):
            clean_mode = "buttons"

        panel_id = await self.bot.db.execute(
            """
            INSERT INTO reaction_role_panels (
                guild_id, channel_id, panel_title, panel_description,
                panel_mode, exclusive_group, max_roles_per_user, entries_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, '[]');
            """,
            (
                int(interaction.guild.id),
                int(interaction.channel.id),
                title,
                description,
                clean_mode,
                1 if exclusive else 0,
                max(0, int(max_roles)),
            ),
        )
        embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
        embed.set_footer(text=f"Reaction Role Panel #{panel_id} · Mode: {clean_mode}")
        msg = await interaction.channel.send(embed=embed)
        await self.bot.db.execute(
            "UPDATE reaction_role_panels SET message_id = ? WHERE panel_id = ?;",
            (int(msg.id), panel_id),
        )
        await interaction.response.send_message(
            f"Created Reaction Role Panel `#{panel_id}` (`{title}`). Use `/reactionrole add` to add roles to it.",
            ephemeral=True,
        )

    @reactionrole_group.command(name="edit", description="Edit an existing Reaction Role panel's title, description, or limits.")
    @app_commands.describe(
        panel_id="ID of the Reaction Role panel",
        title="Updated panel title",
        description="Updated panel description",
        exclusive="Exclusive group mode (1 role at a time)",
        max_roles="Max roles per user (0 = unlimited)",
    )
    @require_permission_level(PermissionLevel.ADMIN, module_name="reaction_roles")
    async def rr_edit(
        self,
        interaction: discord.Interaction,
        panel_id: int,
        title: str,
        description: str,
        exclusive: bool = False,
        max_roles: int = 0,
    ) -> None:
        if interaction.guild is None:
            return
        panel = await self.bot.db.fetch_one(
            "SELECT * FROM reaction_role_panels WHERE panel_id = ? AND guild_id = ?;",
            (int(panel_id), int(interaction.guild.id)),
        )
        if not panel:
            await interaction.response.send_message(f"Reaction Role Panel `#{panel_id}` not found.", ephemeral=True)
            return
        await self.bot.db.execute(
            """
            UPDATE reaction_role_panels
            SET panel_title = ?, panel_description = ?, exclusive_group = ?, max_roles_per_user = ?
            WHERE panel_id = ? AND guild_id = ?;
            """,
            (title, description, 1 if exclusive else 0, max(0, int(max_roles)), int(panel_id), int(interaction.guild.id)),
        )
        await interaction.response.send_message(f"Updated Reaction Role Panel `#{panel_id}`.", ephemeral=True)

    @reactionrole_group.command(name="delete", description="Delete a Reaction Role panel from the database.")
    @app_commands.describe(panel_id="Panel ID to delete")
    @require_permission_level(PermissionLevel.ADMIN, module_name="reaction_roles")
    async def rr_delete(self, interaction: discord.Interaction, panel_id: int) -> None:
        if interaction.guild is None:
            return
        await self.bot.db.execute(
            "DELETE FROM reaction_role_panels WHERE panel_id = ? AND guild_id = ?;",
            (int(panel_id), int(interaction.guild.id)),
        )
        await interaction.response.send_message(f"Deleted Reaction Role Panel `#{panel_id}`.", ephemeral=True)

    @reactionrole_group.command(name="list", description="List all Reaction Role panels in this server.")
    async def rr_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        rows = await self.bot.db.fetch_all(
            "SELECT * FROM reaction_role_panels WHERE guild_id = ? ORDER BY panel_id ASC;",
            (int(interaction.guild.id),),
        )
        embed = discord.Embed(title=f"Reaction Role Panels ({len(rows)})", color=discord.Color.blurple())
        if not rows:
            embed.description = "No Reaction Role panels configured yet. Run `/reactionrole create`."
        else:
            lines = []
            for r in rows:
                entries = json.loads(r.get("entries_json") or "[]")
                lines.append(
                    f"`Panel #{r['panel_id']}` — **{r['panel_title']}** (<#{r['channel_id']}>) · "
                    f"Mode: `{r['panel_mode']}` · Roles: **{len(entries)}** · Exclusive: `{bool(r['exclusive_group'])}`"
                )
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @reactionrole_group.command(name="add", description="Add a self-assignable role to a Reaction Role panel (with hierarchy check).")
    @app_commands.describe(panel_id="Target Panel ID", role="Role to add", label="Button/Dropdown label", emoji="Optional emoji")
    @require_permission_level(PermissionLevel.ADMIN, module_name="reaction_roles")
    async def rr_add(
        self,
        interaction: discord.Interaction,
        panel_id: int,
        role: discord.Role,
        label: Optional[str] = None,
        emoji: str = "✨",
    ) -> None:
        if interaction.guild is None:
            return
        safe, msg = validate_assignable_role(role, interaction.guild)
        if not safe:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        panel = await self.bot.db.fetch_one(
            "SELECT * FROM reaction_role_panels WHERE panel_id = ? AND guild_id = ?;",
            (int(panel_id), int(interaction.guild.id)),
        )
        if not panel:
            await interaction.response.send_message(f"Panel `#{panel_id}` not found.", ephemeral=True)
            return

        entries = json.loads(panel.get("entries_json") or "[]")
        entries = [e for e in entries if int(e["role_id"]) != int(role.id)]
        entries.append({"role_id": int(role.id), "label": label or role.name, "emoji": emoji})

        await self.bot.db.execute(
            "UPDATE reaction_role_panels SET entries_json = ? WHERE panel_id = ?;",
            (json.dumps(entries), int(panel_id)),
        )

        # Republish updated persistent view to channel
        view = PersistentReactionRoleView(self.bot, panel_id=int(panel_id), entries=entries)
        embed = discord.Embed(
            title=panel["panel_title"],
            description=panel["panel_description"]
            + "\n\n"
            + "\n".join(f"{e.get('emoji', '•')} <@&{e['role_id']}> — **{e['label']}**" for e in entries),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"Reaction Role Panel #{panel_id} · Click a button to toggle role")
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            f"Added role {role.mention} to Panel `#{panel_id}` and published updated panel.",
            ephemeral=True,
        )

    @reactionrole_group.command(name="remove", description="Remove a role from a Reaction Role panel.")
    @app_commands.describe(panel_id="Target Panel ID", role="Role to remove from the panel")
    @require_permission_level(PermissionLevel.ADMIN, module_name="reaction_roles")
    async def rr_remove(
        self,
        interaction: discord.Interaction,
        panel_id: int,
        role: discord.Role,
    ) -> None:
        if interaction.guild is None:
            return
        panel = await self.bot.db.fetch_one(
            "SELECT * FROM reaction_role_panels WHERE panel_id = ? AND guild_id = ?;",
            (int(panel_id), int(interaction.guild.id)),
        )
        if not panel:
            await interaction.response.send_message(f"Panel `#{panel_id}` not found.", ephemeral=True)
            return
        entries = json.loads(panel.get("entries_json") or "[]")
        entries = [e for e in entries if int(e["role_id"]) != int(role.id)]
        await self.bot.db.execute(
            "UPDATE reaction_role_panels SET entries_json = ? WHERE panel_id = ?;",
            (json.dumps(entries), int(panel_id)),
        )
        await interaction.response.send_message(
            f"Removed role {role.mention} from Panel `#{panel_id}`.",
            ephemeral=True,
        )


async def setup(bot: "CosmicBot") -> None:
    await bot.add_cog(ReactionRolesCog(bot))
