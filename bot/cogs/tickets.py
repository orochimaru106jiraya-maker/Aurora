"""
Advanced Ticket Management Cog (`/jticket`) for Cosmic ki baddie (HIGHEST PRIORITY).

Implements all 16 required `/jticket` slash commands:
- `/jticket setup`
- `/jticket panel`
- `/jticket config`
- `/jticket open`
- `/jticket close`
- `/jticket reopen`
- `/jticket delete`
- `/jticket claim`
- `/jticket unclaim`
- `/jticket transfer`
- `/jticket add`
- `/jticket remove`
- `/jticket rename`
- `/jticket transcript`
- `/jticket stats`
- `/jticket list`
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Optional

from bot.core.discord_compat import app_commands, commands, discord
from bot.database.models import PermissionLevel, TicketCategoryKey
from bot.ui.dashboard import SetupDashboardView
from bot.ui.persistent_views import PersistentTicketChannelView, PersistentTicketPanelView
from bot.utils.checks import require_permission_level
from bot.utils.formatting import sanitize_channel_name

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot


class TicketsCog(commands.Cog):
    """Full-featured 4-category ticket management system under `/jticket`."""

    jticket_group = app_commands.Group(
        name="jticket",
        description="Manage the 4-category support ticket platform, panels, transcripts, and staff assignments.",
    )

    def __init__(self, bot: "CosmicBot") -> None:
        self.bot = bot

    @jticket_group.command(name="setup", description="Launch the interactive Ticket System Setup Dashboard for all 4 categories.")
    @require_permission_level(PermissionLevel.ADMIN, module_name="tickets")
    async def jticket_setup(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await self.bot.ticket_service.ensure_default_categories(int(interaction.guild.id))
        view = SetupDashboardView(self.bot, author_id=int(interaction.user.id), initial_page="tickets")
        embed = await view.build_page_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @jticket_group.command(name="panel", description="Publish the persistent 4-category interactive ticket creation panel.")
    @app_commands.describe(channel="Target text channel for the ticket panel (defaults to current channel)")
    @require_permission_level(PermissionLevel.ADMIN, module_name="tickets")
    async def jticket_panel(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if interaction.guild is None:
            return
        target_ch = channel or interaction.channel
        cats = await self.bot.ticket_service.ensure_default_categories(int(interaction.guild.id))

        embed = discord.Embed(
            title=f"{interaction.guild.name} — Official Support & Ticket Center",
            description=(
                "Click the button matching your request below to open a private ticket channel with our staff team:\n\n"
                + "\n".join(
                    f"**{c['emoji']} {c['display_name']}** — {c['description']}"
                    for c in cats
                )
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Cosmic ki baddie Ticket System · Automatic transcript & DM notifications enabled")
        view = PersistentTicketPanelView(self.bot)
        await target_ch.send(embed=embed, view=view)
        await interaction.response.send_message(
            f"Published 4-category Ticket Panel in {target_ch.mention}.",
            ephemeral=True,
        )

    @jticket_group.command(name="config", description="Configure a specific ticket category's channel category, staff role, limits, and transcript channel.")
    @app_commands.describe(
        category_key="Category key: general_help, file_complaint, staff_application, or claim_prize",
        discord_category="Discord CategoryChannel where new tickets of this type will be created",
        staff_role="Staff role authorized to view and claim tickets in this category",
        transcript_channel="Channel where closed ticket transcripts are archived",
        max_open_per_user="Maximum simultaneous open tickets per user in this category",
        auto_delete_seconds="Seconds to retain closed ticket channel before deletion",
        naming_format="Channel naming pattern (e.g. help-{username}-{id})",
    )
    @require_permission_level(PermissionLevel.ADMIN, module_name="tickets")
    async def jticket_config(
        self,
        interaction: discord.Interaction,
        category_key: str,
        discord_category: Optional[discord.CategoryChannel] = None,
        staff_role: Optional[discord.Role] = None,
        transcript_channel: Optional[discord.TextChannel] = None,
        max_open_per_user: Optional[int] = None,
        auto_delete_seconds: Optional[int] = None,
        naming_format: Optional[str] = None,
    ) -> None:
        if interaction.guild is None:
            return
        guild_id = int(interaction.guild.id)
        existing = await self.bot.ticket_service.get_category_config(guild_id, category_key.strip().lower())
        if not existing:
            await interaction.response.send_message(
                "Invalid `category_key`. Choose from: `general_help`, `file_complaint`, `staff_application`, `claim_prize`.",
                ephemeral=True,
            )
            return

        updates = {}
        if discord_category is not None:
            updates["discord_category_id"] = int(discord_category.id)
        if staff_role is not None:
            roles = set(json.loads(existing.get("staff_role_ids_json") or "[]"))
            roles.add(int(staff_role.id))
            updates["staff_role_ids_json"] = json.dumps(list(roles))
        if transcript_channel is not None:
            updates["transcript_channel_id"] = int(transcript_channel.id)
        if max_open_per_user is not None:
            updates["max_open_per_user"] = max(1, min(10, int(max_open_per_user)))
        if auto_delete_seconds is not None:
            updates["auto_delete_seconds"] = max(10, int(auto_delete_seconds))
        if naming_format is not None:
            updates["naming_format"] = naming_format.strip()

        updated = await self.bot.ticket_service.update_category_config(guild_id, category_key.strip().lower(), **updates)
        embed = discord.Embed(
            title=f"Updated Ticket Category: {updated['emoji']} {updated['display_name']}",
            color=discord.Color.green(),
        )
        embed.add_field(name="Naming Format", value=f"`{updated['naming_format']}`", inline=True)
        embed.add_field(name="Max Open / User", value=str(updated["max_open_per_user"]), inline=True)
        embed.add_field(name="Retention Period", value=f"`{updated['auto_delete_seconds']}s`", inline=True)
        embed.add_field(name="Staff Roles", value=f"`{updated['staff_role_ids_json']}`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @jticket_group.command(name="open", description="Directly open a new support ticket in one of the 4 categories.")
    @app_commands.describe(
        category_key="Category: general_help, file_complaint, staff_application, or claim_prize",
        subject="Brief summary or reason for opening the ticket",
    )
    async def jticket_open(
        self,
        interaction: discord.Interaction,
        category_key: str = TicketCategoryKey.GENERAL_HELP.value,
        subject: str = "General support request",
    ) -> None:
        if interaction.guild is None:
            return
        ok, msg, record, channel = await self.bot.ticket_service.open_ticket(
            guild=interaction.guild,
            creator=interaction.user,
            category_key=category_key.strip().lower(),
            form_responses={"Initial Subject": subject},
        )
        if not ok or record is None or channel is None:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Ticket #{record['ticket_number']:04d} Opened",
            description=f"Creator: <@{interaction.user.id}>\nCategory: `{category_key}`\nSubject: {subject}",
            color=discord.Color.blurple(),
        )
        await channel.send(embed=embed, view=PersistentTicketChannelView(self.bot))
        await interaction.response.send_message(msg, ephemeral=True)

    @jticket_group.command(name="close", description="Close the current ticket, archive transcript, and DM creator & claiming moderator.")
    @app_commands.describe(reason="Reason for closing the ticket")
    @require_permission_level(PermissionLevel.TICKET_STAFF, module_name="tickets")
    async def jticket_close(self, interaction: discord.Interaction, reason: str = "Resolved by support staff") -> None:
        if interaction.guild is None:
            return
        ok, msg, _ = await self.bot.ticket_service.close_ticket(
            guild=interaction.guild,
            channel=interaction.channel,
            closing_moderator=interaction.user,
            reason=reason,
        )
        await interaction.response.send_message(msg, ephemeral=not ok)

    @jticket_group.command(name="reopen", description="Reopen a previously closed ticket channel and restore creator access.")
    @require_permission_level(PermissionLevel.TICKET_STAFF, module_name="tickets")
    async def jticket_reopen(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        ok, msg, _ = await self.bot.ticket_service.reopen_ticket(interaction.guild, interaction.channel)
        await interaction.response.send_message(msg, ephemeral=not ok)

    @jticket_group.command(name="delete", description="Permanently delete a ticket channel after saving its status.")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="tickets")
    async def jticket_delete(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        ticket = await self.bot.ticket_service.get_ticket_by_channel(int(interaction.channel.id))
        if not ticket:
            await interaction.response.send_message("This channel is not a registered ticket.", ephemeral=True)
            return
        await self.bot.db.execute(
            "UPDATE tickets SET status = 'deleted', closed_at = COALESCE(closed_at, datetime('now')) WHERE ticket_id = ?;",
            (int(ticket["ticket_id"]),),
        )
        await interaction.response.send_message(f"Deleting Ticket `#{ticket['ticket_number']:04d}`...")
        await interaction.channel.delete(reason=f"Ticket #{ticket['ticket_number']:04d} deleted by {interaction.user.name}")

    @jticket_group.command(name="claim", description="Claim responsibility for handling the current ticket.")
    @require_permission_level(PermissionLevel.TICKET_STAFF, module_name="tickets")
    async def jticket_claim(self, interaction: discord.Interaction) -> None:
        ok, msg, _ = await self.bot.ticket_service.claim_ticket(int(interaction.channel.id), int(interaction.user.id))
        await interaction.response.send_message(msg, ephemeral=not ok)

    @jticket_group.command(name="unclaim", description="Release your claim on the current ticket so other staff can claim it.")
    @require_permission_level(PermissionLevel.TICKET_STAFF, module_name="tickets")
    async def jticket_unclaim(self, interaction: discord.Interaction) -> None:
        ok, msg, _ = await self.bot.ticket_service.unclaim_ticket(int(interaction.channel.id), int(interaction.user.id))
        await interaction.response.send_message(msg, ephemeral=not ok)

    @jticket_group.command(name="transfer", description="Transfer claim ownership of the current ticket to another staff member.")
    @app_commands.describe(staff_member="The staff member to transfer this ticket to")
    @require_permission_level(PermissionLevel.TICKET_STAFF, module_name="tickets")
    async def jticket_transfer(self, interaction: discord.Interaction, staff_member: discord.Member) -> None:
        ok, msg, _ = await self.bot.ticket_service.transfer_ticket(int(interaction.channel.id), int(staff_member.id))
        await interaction.response.send_message(msg, ephemeral=not ok)

    @jticket_group.command(name="add", description="Add a user to the current ticket channel.")
    @app_commands.describe(member="Member to grant read/write access in this ticket")
    @require_permission_level(PermissionLevel.TICKET_STAFF, module_name="tickets")
    async def jticket_add(self, interaction: discord.Interaction, member: discord.Member) -> None:
        ticket = await self.bot.ticket_service.get_ticket_by_channel(int(interaction.channel.id))
        if not ticket:
            await interaction.response.send_message("This channel is not a registered ticket.", ephemeral=True)
            return
        await interaction.channel.set_permissions(
            member,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
        )
        await interaction.response.send_message(f"Added {member.mention} to Ticket `#{ticket['ticket_number']:04d}`.")

    @jticket_group.command(name="remove", description="Remove a user from the current ticket channel.")
    @app_commands.describe(member="Member to revoke access from in this ticket")
    @require_permission_level(PermissionLevel.TICKET_STAFF, module_name="tickets")
    async def jticket_remove(self, interaction: discord.Interaction, member: discord.Member) -> None:
        ticket = await self.bot.ticket_service.get_ticket_by_channel(int(interaction.channel.id))
        if not ticket:
            await interaction.response.send_message("This channel is not a registered ticket.", ephemeral=True)
            return
        await interaction.channel.set_permissions(member, view_channel=False, send_messages=False)
        await interaction.response.send_message(f"Removed {member.mention} from Ticket `#{ticket['ticket_number']:04d}`.")

    @jticket_group.command(name="rename", description="Rename the current ticket channel.")
    @app_commands.describe(new_name="New channel name")
    @require_permission_level(PermissionLevel.TICKET_STAFF, module_name="tickets")
    async def jticket_rename(self, interaction: discord.Interaction, new_name: str) -> None:
        ticket = await self.bot.ticket_service.get_ticket_by_channel(int(interaction.channel.id))
        if not ticket:
            await interaction.response.send_message("This channel is not a registered ticket.", ephemeral=True)
            return
        slug = sanitize_channel_name(new_name, fallback=f"ticket-{ticket['ticket_number']:04d}")
        await interaction.channel.edit(name=slug)
        await interaction.response.send_message(f"Renamed ticket channel to `{slug}`.")

    @jticket_group.command(name="transcript", description="Generate and download a complete transcript of the current ticket.")
    @require_permission_level(PermissionLevel.TICKET_STAFF, module_name="tickets")
    async def jticket_transcript(self, interaction: discord.Interaction) -> None:
        ticket = await self.bot.ticket_service.get_ticket_by_channel(int(interaction.channel.id))
        if not ticket:
            await interaction.response.send_message("This channel is not a registered ticket.", ephemeral=True)
            return
        text = await self.bot.ticket_service.generate_transcript(
            guild=interaction.guild,
            channel=interaction.channel,
            ticket=ticket,
            closing_moderator=interaction.user,
            close_reason="Manual /jticket transcript export",
        )
        file_obj = discord.File(
            io.BytesIO(text.encode("utf-8")),
            filename=f"ticket-{ticket['ticket_number']:04d}-transcript.txt",
        )
        await interaction.response.send_message(
            f"Generated transcript for Ticket `#{ticket['ticket_number']:04d}`:",
            file=file_obj,
            ephemeral=True,
        )

    @jticket_group.command(name="stats", description="View server ticket statistics across all 4 categories.")
    @require_permission_level(PermissionLevel.TICKET_STAFF, module_name="tickets")
    async def jticket_stats(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        stats = await self.bot.ticket_service.get_ticket_statistics(int(interaction.guild.id))
        embed = discord.Embed(
            title=f"Ticket Analytics — {interaction.guild.name}",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Total Tickets", value=str(stats["total"]), inline=True)
        embed.add_field(name="Open / Active", value=str(stats["open"]), inline=True)
        embed.add_field(name="Claimed by Staff", value=str(stats["claimed"]), inline=True)
        embed.add_field(name="Closed & Archived", value=str(stats["closed"]), inline=True)
        cat_lines = [f"• `{k}`: **{v}**" for k, v in stats["by_category"].items()] or ["No tickets created yet."]
        embed.add_field(name="Breakdown by Category", value="\n".join(cat_lines), inline=False)
        await interaction.response.send_message(embed=embed)

    @jticket_group.command(name="list", description="List all currently open or claimed tickets in this server.")
    @require_permission_level(PermissionLevel.TICKET_STAFF, module_name="tickets")
    async def jticket_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        rows = await self.bot.db.fetch_all(
            """
            SELECT * FROM tickets
            WHERE guild_id = ? AND status IN ('open', 'claimed')
            ORDER BY ticket_number DESC LIMIT 25;
            """,
            (int(interaction.guild.id),),
        )
        embed = discord.Embed(
            title=f"Active Server Tickets ({len(rows)})",
            color=discord.Color.blurple(),
        )
        if not rows:
            embed.description = "There are currently no open tickets."
        else:
            lines = []
            for r in rows:
                claimed_str = f"<@{r['claimed_by_id']}>" if r.get("claimed_by_id") else "Unclaimed"
                lines.append(
                    f"`#{r['ticket_number']:04d}` · <#{r['channel_id']}> · Creator: <@{r['creator_id']}> · "
                    f"Category: `{r['category_key']}` · Claimed: {claimed_str}"
                )
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: "CosmicBot") -> None:
    await bot.add_cog(TicketsCog(bot))
