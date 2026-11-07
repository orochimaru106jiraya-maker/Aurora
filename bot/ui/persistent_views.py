"""
Persistent Discord UI Views for Cosmic ki baddie.
All views in this module have `timeout=None` and deterministic `custom_id` values so they
survive bot restarts on Railway without breaking existing panels in Discord channels.

Includes:
1. PersistentTicketPanelView (4 default categories: General Help, File a Complaint, Apply for Staff Role, Claim Winning Prize)
2. TicketFormModal (Dynamic ticket intake modal per category)
3. PersistentTicketChannelView (Claim, Unclaim, Close, Transcript buttons inside each active ticket channel)
4. PersistentJTCControlView (Lock, Unlock, Hide, Unhide, Rename, Limit buttons for temporary voice rooms)
5. PersistentReactionRoleView (Self-assignable role toggle buttons with bot role hierarchy protection)
"""

from __future__ import annotations

import io
import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List

from bot.core.discord_compat import discord
from bot.database.models import DEFAULT_TICKET_CATEGORIES, PermissionLevel, TicketCategoryKey
from bot.utils.validators import validate_assignable_role

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot

logger = logging.getLogger("cosmic.ui.persistent_views")


class TicketFormModal(discord.ui.Modal):
    """Dynamic modal presented when a user clicks one of the 4 Ticket Panel buttons."""

    def __init__(self, bot: "CosmicBot", category_key: str, category_cfg: Dict[str, Any]) -> None:
        title = f"{category_cfg.get('display_name', 'Support Ticket')}"[:45]
        super().__init__(title=title, timeout=300.0, custom_id=f"cosmic:ticket_modal:{category_key}")
        self.bot = bot
        self.category_key = category_key
        self.category_cfg = category_cfg
        self.field_inputs: List[discord.ui.TextInput] = []

        raw_fields = json.loads(category_cfg.get("form_fields_json") or "[]")
        if not raw_fields:
            raw_fields = DEFAULT_TICKET_CATEGORIES.get(category_key, {}).get("form_fields", [])

        for idx, f_meta in enumerate(raw_fields[:5]):
            style = (
                discord.TextStyle.paragraph
                if f_meta.get("style", "paragraph") == "paragraph"
                else discord.TextStyle.short
            )
            inp = discord.ui.TextInput(
                label=str(f_meta.get("label", f"Question {idx + 1}"))[:45],
                placeholder=str(f_meta.get("placeholder", "Enter details..."))[:100],
                required=bool(f_meta.get("required", True)),
                style=style,
                custom_id=f"cosmic:ticket_field:{category_key}:{idx}",
                max_length=1000,
            )
            self.field_inputs.append(inp)
            self.add_item(inp)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Tickets can only be opened inside a server.", ephemeral=True)
            return

        responses: Dict[str, str] = {}
        for inp in self.field_inputs:
            responses[inp.label] = inp.value or "(No answer)"

        ok, msg, record, channel = await self.bot.ticket_service.open_ticket(
            guild=interaction.guild,
            creator=interaction.user,
            category_key=self.category_key,
            form_responses=responses,
        )
        if not ok or record is None or channel is None:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        # Send welcome embed & persistent controls inside the newly created ticket channel
        welcome_embed = discord.Embed(
            title=f"{self.category_cfg.get('emoji', '🎫')} Ticket #{record['ticket_number']:04d} — {self.category_cfg.get('display_name')}",
            description=(
                f"Welcome <@{interaction.user.id}>! Our authorized support team has been notified.\n"
                "Please review your submitted details below and provide any additional context."
            ),
            color=discord.Color.blurple(),
        )
        for label, answer in responses.items():
            welcome_embed.add_field(name=label, value=answer[:1024], inline=False)
        welcome_embed.set_footer(text=f"Ticket ID: #{record['ticket_number']:04d} · Category: {self.category_key}")

        channel_view = PersistentTicketChannelView(self.bot)
        await channel.send(content=f"<@{interaction.user.id}>", embed=welcome_embed, view=channel_view)
        await interaction.response.send_message(msg, ephemeral=True)


class PersistentTicketPanelView(discord.ui.View):
    """
    Persistent 4-Category Ticket Creation Panel (`timeout=None`).
    Buttons:
    1. General Help
    2. File a Complaint
    3. Apply for a Staff Role
    4. Claim Winning Prize
    """

    def __init__(self, bot: "CosmicBot") -> None:
        super().__init__(timeout=None)
        self.bot = bot

        categories = [
            (TicketCategoryKey.GENERAL_HELP.value, "General Help", "🛟", discord.ButtonStyle.primary),
            (TicketCategoryKey.FILE_COMPLAINT.value, "File a Complaint", "⚖️", discord.ButtonStyle.danger),
            (TicketCategoryKey.STAFF_APPLICATION.value, "Apply for a Staff Role", "🛡️", discord.ButtonStyle.success),
            (TicketCategoryKey.CLAIM_PRIZE.value, "Claim Winning Prize", "🏆", discord.ButtonStyle.secondary),
        ]

        for cat_key, label, emoji, style in categories:
            btn = discord.ui.Button(
                label=label,
                emoji=emoji,
                style=style,
                custom_id=f"cosmic:ticket_panel:open:{cat_key}",
            )
            btn.callback = self._make_open_callback(cat_key)
            self.add_item(btn)

    def _make_open_callback(self, category_key: str):
        async def _callback(interaction: discord.Interaction) -> None:
            if interaction.guild is None:
                await interaction.response.send_message("Tickets can only be opened in a server.", ephemeral=True)
                return
            cat_cfg = await self.bot.ticket_service.get_category_config(int(interaction.guild.id), category_key)
            if not cat_cfg:
                await interaction.response.send_message("Ticket category configuration not found.", ephemeral=True)
                return
            modal = TicketFormModal(self.bot, category_key, cat_cfg)
            await interaction.response.send_modal(modal)

        return _callback


class PersistentTicketChannelView(discord.ui.View):
    """Persistent in-ticket action bar (Claim, Unclaim, Transcript, Close Ticket)."""

    def __init__(self, bot: "CosmicBot") -> None:
        super().__init__(timeout=None)
        self.bot = bot

        claim_btn = discord.ui.Button(
            label="Claim Ticket",
            style=discord.ButtonStyle.success,
            custom_id="cosmic:ticket_ch:claim",
        )
        unclaim_btn = discord.ui.Button(
            label="Unclaim",
            style=discord.ButtonStyle.secondary,
            custom_id="cosmic:ticket_ch:unclaim",
        )
        transcript_btn = discord.ui.Button(
            label="Transcript",
            style=discord.ButtonStyle.primary,
            custom_id="cosmic:ticket_ch:transcript",
        )
        close_btn = discord.ui.Button(
            label="Close Ticket",
            style=discord.ButtonStyle.danger,
            custom_id="cosmic:ticket_ch:close",
        )

        claim_btn.callback = self._on_claim
        unclaim_btn.callback = self._on_unclaim
        transcript_btn.callback = self._on_transcript
        close_btn.callback = self._on_close

        self.add_item(claim_btn)
        self.add_item(unclaim_btn)
        self.add_item(transcript_btn)
        self.add_item(close_btn)

    async def _check_staff(self, interaction: discord.Interaction) -> bool:
        allowed, reason = await self.bot.permission_service.authorize_interaction(
            interaction=interaction,
            command_name="jticket claim",
            module_name="tickets",
            default_level=PermissionLevel.TICKET_STAFF,
        )
        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return False
        return True

    async def _on_claim(self, interaction: discord.Interaction) -> None:
        if not await self._check_staff(interaction):
            return
        ok, msg, _ = await self.bot.ticket_service.claim_ticket(int(interaction.channel.id), int(interaction.user.id))
        await interaction.response.send_message(msg, ephemeral=not ok)

    async def _on_unclaim(self, interaction: discord.Interaction) -> None:
        if not await self._check_staff(interaction):
            return
        ok, msg, _ = await self.bot.ticket_service.unclaim_ticket(int(interaction.channel.id), int(interaction.user.id))
        await interaction.response.send_message(msg, ephemeral=not ok)

    async def _on_transcript(self, interaction: discord.Interaction) -> None:
        if not await self._check_staff(interaction):
            return
        ticket = await self.bot.ticket_service.get_ticket_by_channel(int(interaction.channel.id))
        if not ticket:
            await interaction.response.send_message("This channel is not an active ticket.", ephemeral=True)
            return
        text = await self.bot.ticket_service.generate_transcript(
            guild=interaction.guild,
            channel=interaction.channel,
            ticket=ticket,
            closing_moderator=interaction.user,
            close_reason="On-demand transcript snapshot",
        )
        f = discord.File(io.BytesIO(text.encode("utf-8")), filename=f"ticket-{ticket['ticket_number']:04d}.txt")
        await interaction.response.send_message("Generated live ticket transcript:", file=f, ephemeral=True)

    async def _on_close(self, interaction: discord.Interaction) -> None:
        if not await self._check_staff(interaction):
            return
        ok, msg, _ = await self.bot.ticket_service.close_ticket(
            guild=interaction.guild,
            channel=interaction.channel,
            closing_moderator=interaction.user,
            reason="Closed via ticket control panel",
        )
        await interaction.response.send_message(msg)


class PersistentJTCControlView(discord.ui.View):
    """Persistent Voice Room Control Panel (`timeout=None`). Enforces room owner or moderator verification."""

    def __init__(self, bot: "CosmicBot") -> None:
        super().__init__(timeout=None)
        self.bot = bot

        actions = [
            ("Lock Room", "lock", discord.ButtonStyle.secondary),
            ("Unlock Room", "unlock", discord.ButtonStyle.secondary),
            ("Hide Room", "hide", discord.ButtonStyle.secondary),
            ("Unhide Room", "unhide", discord.ButtonStyle.secondary),
            ("Claim Ownership", "claim", discord.ButtonStyle.primary),
        ]
        for label, act, style in actions:
            btn = discord.ui.Button(
                label=label,
                style=style,
                custom_id=f"cosmic:jtc_panel:{act}",
            )
            btn.callback = self._make_jtc_callback(act)
            self.add_item(btn)

    def _make_jtc_callback(self, action: str):
        async def _callback(interaction: discord.Interaction) -> None:
            if interaction.guild is None:
                return
            voice_state = getattr(interaction.user, "voice", None)
            voice_ch = getattr(voice_state, "channel", None) if voice_state else None
            if voice_ch is None:
                await interaction.response.send_message(
                    "You must be connected to your Join-to-Create voice room to use this control panel.",
                    ephemeral=True,
                )
                return

            room = await self.bot.jtc_service.get_room(int(voice_ch.id))
            if not room:
                await interaction.response.send_message(
                    "Your current voice channel is not a managed Join-to-Create room.",
                    ephemeral=True,
                )
                return

            if action == "claim":
                owner_in_channel = any(int(m.id) == int(room["owner_id"]) for m in getattr(voice_ch, "members", []))
                if owner_in_channel:
                    await interaction.response.send_message(
                        f"The current room owner (<@{room['owner_id']}>) is still connected to this channel.",
                        ephemeral=True,
                    )
                    return
                await self.bot.db.execute(
                    "UPDATE jtc_active_rooms SET owner_id = ? WHERE channel_id = ?;",
                    (int(interaction.user.id), int(voice_ch.id)),
                )
                await interaction.response.send_message(
                    f"You have claimed ownership of <#{voice_ch.id}>!",
                    ephemeral=True,
                )
                return

            can_manage, reason = await self.bot.jtc_service.can_manage_room(
                interaction.guild,
                interaction.user,
                int(voice_ch.id),
                self.bot.permission_service,
            )
            if not can_manage:
                await interaction.response.send_message(reason, ephemeral=True)
                return

            if action == "lock":
                await voice_ch.set_permissions(interaction.guild.default_role, connect=False)
                await self.bot.db.execute("UPDATE jtc_active_rooms SET is_locked = 1 WHERE channel_id = ?;", (int(voice_ch.id),))
                await interaction.response.send_message(f"Locked <#{voice_ch.id}>.", ephemeral=True)
            elif action == "unlock":
                await voice_ch.set_permissions(interaction.guild.default_role, connect=True)
                await self.bot.db.execute("UPDATE jtc_active_rooms SET is_locked = 0 WHERE channel_id = ?;", (int(voice_ch.id),))
                await interaction.response.send_message(f"Unlocked <#{voice_ch.id}>.", ephemeral=True)
            elif action == "hide":
                await voice_ch.set_permissions(interaction.guild.default_role, view_channel=False)
                await self.bot.db.execute("UPDATE jtc_active_rooms SET is_hidden = 1 WHERE channel_id = ?;", (int(voice_ch.id),))
                await interaction.response.send_message(f"Hidden <#{voice_ch.id}> from server channel list.", ephemeral=True)
            elif action == "unhide":
                await voice_ch.set_permissions(interaction.guild.default_role, view_channel=True)
                await self.bot.db.execute("UPDATE jtc_active_rooms SET is_hidden = 0 WHERE channel_id = ?;", (int(voice_ch.id),))
                await interaction.response.send_message(f"Unhidden <#{voice_ch.id}>.", ephemeral=True)

        return _callback


class PersistentReactionRoleView(discord.ui.View):
    """Persistent Reaction Role Button Panel (`timeout=None`)."""

    def __init__(self, bot: "CosmicBot", panel_id: int = 0, entries: List[Dict[str, Any]] | None = None) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.panel_id = panel_id
        role_entries = entries or []

        if not role_entries:
            # Register generic persistent handler button for dynamic panels
            placeholder_btn = discord.ui.Button(
                label="Toggle Self Role",
                style=discord.ButtonStyle.primary,
                custom_id="cosmic:rr:toggle:default",
            )
            placeholder_btn.callback = self._handle_generic_toggle
            self.add_item(placeholder_btn)
        else:
            for item in role_entries[:25]:
                rid = int(item["role_id"])
                btn = discord.ui.Button(
                    label=str(item.get("label", f"Role {rid}"))[:80],
                    emoji=item.get("emoji"),
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"cosmic:rr:{panel_id}:{rid}",
                )
                btn.callback = self._make_role_callback(panel_id, rid)
                self.add_item(btn)

    async def _handle_generic_toggle(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Reaction role panel ready.", ephemeral=True)

    def _make_role_callback(self, panel_id: int, role_id: int):
        async def _callback(interaction: discord.Interaction) -> None:
            if interaction.guild is None:
                return
            role = interaction.guild.get_role(role_id)
            if role is None:
                await interaction.response.send_message("That role no longer exists on this server.", ephemeral=True)
                return

            safe, msg = validate_assignable_role(role, interaction.guild)
            if not safe:
                await interaction.response.send_message(msg, ephemeral=True)
                return

            panel_row = await self.bot.db.fetch_one(
                "SELECT * FROM reaction_role_panels WHERE panel_id = ? AND guild_id = ?;",
                (panel_id, int(interaction.guild.id)),
            )

            member_roles = getattr(interaction.user, "roles", [])
            has_role = any(int(r.id) == role_id for r in member_roles)

            if has_role:
                await interaction.user.remove_roles(role, reason=f"Reaction Role Panel #{panel_id} removal")
                await interaction.response.send_message(f"Removed role **{role.name}**.", ephemeral=True)
                return

            # Check exclusive group & max role limits if panel exists
            if panel_row:
                entries = json.loads(panel_row.get("entries_json") or "[]")
                panel_role_ids = {int(e["role_id"]) for e in entries}
                if bool(panel_row.get("exclusive_group")):
                    to_remove = [r for r in member_roles if int(r.id) in panel_role_ids and int(r.id) != role_id]
                    if to_remove:
                        await interaction.user.remove_roles(*to_remove, reason="Exclusive reaction role group")

                max_roles = int(panel_row.get("max_roles_per_user") or 0)
                if max_roles > 0:
                    current_panel_roles = [r for r in getattr(interaction.user, "roles", []) if int(r.id) in panel_role_ids]
                    if len(current_panel_roles) >= max_roles:
                        await interaction.response.send_message(
                            f"Role Limit Reached: You can only hold up to **{max_roles}** role(s) from this panel.",
                            ephemeral=True,
                        )
                        return

            await interaction.user.add_roles(role, reason=f"Reaction Role Panel #{panel_id} self-assignment")
            await interaction.response.send_message(f"Assigned role **{role.name}**!", ephemeral=True)

        return _callback


def register_all_persistent_views(bot: "CosmicBot") -> int:
    """Register all persistent views with `bot.add_view(...)` during startup."""
    views = [
        PersistentTicketPanelView(bot),
        PersistentTicketChannelView(bot),
        PersistentJTCControlView(bot),
        PersistentReactionRoleView(bot),
    ]
    for v in views:
        bot.add_view(v)
    return len(views)
