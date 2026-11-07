"""
Advanced Ticket Management Service for Cosmic ki baddie (HIGHEST PRIORITY).

Implements:
- 4 Default Ticket Categories:
  1. General Help (`general_help`)
  2. File a Complaint (`file_complaint`)
  3. Apply for a Staff Role (`staff_application`)
  4. Claim Winning Prize (`claim_prize`)
- Independent per-category configuration (channel category, staff roles, custom naming, custom modal form fields,
  per-user ticket limits, auto-deletion delay, transcript destination).
- Duplicate open ticket prevention per category.
- Automatic channel permission overwrites (hidden from @everyone, accessible to creator + authorized category staff).
- Claim, Unclaim, Transfer, Add User, Remove User, Rename, Reopen, Delete.
- Complete Closing Pipeline:
  1. Generates structured text transcript.
  2. Saves transcript in configured transcript channel.
  3. DMs the ticket creator with ticket ID, creator, moderator, category, closing reason, and transcript file.
  4. DMs the moderator who claimed the ticket (or if unclaimed, notifies the moderator who closed it).
  5. Gracefully handles failed DMs (Forbidden / closed DMs) without aborting ticket closure.
  6. Preserves the channel until the configured deletion period expires.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from bot.core.discord_compat import discord
from bot.database.manager import DatabaseManager
from bot.database.models import DEFAULT_TICKET_CATEGORIES, TicketCategoryKey
from bot.utils.formatting import sanitize_channel_name, utc_now_iso

logger = logging.getLogger("cosmic.services.ticket")


class TicketService:
    """Business logic and SQLite persistence for the 4-category ticket platform."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    async def ensure_default_categories(self, guild_id: int) -> List[Dict[str, Any]]:
        """Seed the 4 mandatory ticket categories for a guild if not already present."""
        existing = await self.db.fetch_all(
            "SELECT * FROM ticket_categories WHERE guild_id = ? ORDER BY id ASC;",
            (guild_id,),
        )
        existing_keys = {r["category_key"] for r in existing}

        for key, meta in DEFAULT_TICKET_CATEGORIES.items():
            if key not in existing_keys:
                await self.db.execute(
                    """
                    INSERT INTO ticket_categories (
                        guild_id, category_key, display_name, emoji, description,
                        naming_format, max_open_per_user, auto_delete_seconds, form_fields_json, enabled
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(guild_id, category_key) DO NOTHING;
                    """,
                    (
                        guild_id,
                        key,
                        meta["name"],
                        meta["emoji"],
                        meta["description"],
                        meta["naming_format"],
                        meta["max_open_per_user"],
                        meta["auto_delete_delay_seconds"],
                        json.dumps(meta["form_fields"]),
                    ),
                )

        return await self.db.fetch_all(
            "SELECT * FROM ticket_categories WHERE guild_id = ? ORDER BY id ASC;",
            (guild_id,),
        )

    async def get_category_config(self, guild_id: int, category_key: str) -> Optional[Dict[str, Any]]:
        await self.ensure_default_categories(guild_id)
        return await self.db.fetch_one(
            "SELECT * FROM ticket_categories WHERE guild_id = ? AND category_key = ?;",
            (guild_id, category_key),
        )

    async def update_category_config(
        self,
        guild_id: int,
        category_key: str,
        **updates: Any,
    ) -> Optional[Dict[str, Any]]:
        await self.ensure_default_categories(guild_id)
        allowed_cols = {
            "display_name",
            "emoji",
            "description",
            "discord_category_id",
            "transcript_channel_id",
            "staff_role_ids_json",
            "naming_format",
            "max_open_per_user",
            "auto_delete_seconds",
            "form_fields_json",
            "enabled",
        }
        clauses: List[str] = []
        params: List[Any] = []
        for k, v in updates.items():
            if k in allowed_cols:
                clauses.append(f"{k} = ?")
                params.append(v)
        if clauses:
            params.extend([guild_id, category_key])
            await self.db.execute(
                f"UPDATE ticket_categories SET {', '.join(clauses)} WHERE guild_id = ? AND category_key = ?;",
                params,
            )
        return await self.get_category_config(guild_id, category_key)

    async def open_ticket(
        self,
        guild: Any,
        creator: Any,
        category_key: str,
        form_responses: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]], Optional[Any]]:
        """
        Validate limits/duplicates, create the ticket channel with strict permission overwrites,
        and persist the ticket in SQLite.
        Returns `(success, message, ticket_record, channel)`.
        """
        guild_id = int(guild.id)
        creator_id = int(creator.id)
        cat_cfg = await self.get_category_config(guild_id, category_key)
        if not cat_cfg:
            return False, f"Unknown ticket category `{category_key}`.", None, None

        if not bool(cat_cfg.get("enabled", 1)):
            return False, f"The **{cat_cfg['display_name']}** ticket category is currently closed.", None, None

        # Duplicate / limit check
        open_tickets = await self.db.fetch_all(
            """
            SELECT * FROM tickets
            WHERE guild_id = ? AND creator_id = ? AND category_key = ? AND status IN ('open', 'claimed');
            """,
            (guild_id, creator_id, category_key),
        )
        max_open = int(cat_cfg.get("max_open_per_user") or 1)
        if len(open_tickets) >= max_open:
            existing_ch = open_tickets[0]["channel_id"]
            return (
                False,
                f"Duplicate Ticket Prevented: You already have an active **{cat_cfg['display_name']}** ticket (<#{existing_ch}>). "
                f"Limit is {max_open} open ticket(s) per user in this category.",
                None,
                None,
            )

        # Next ticket number in guild
        num_row = await self.db.fetch_one(
            "SELECT COALESCE(MAX(ticket_number), 0) AS max_num FROM tickets WHERE guild_id = ?;",
            (guild_id,),
        )
        next_num = int((num_row or {}).get("max_num", 0)) + 1

        naming_fmt = cat_cfg.get("naming_format") or "ticket-{username}-{id}"
        raw_channel_name = (
            naming_fmt.replace("{username}", getattr(creator, "name", "user"))
            .replace("{id}", f"{next_num:04d}")
            .replace("{category}", category_key)
        )
        channel_name = sanitize_channel_name(raw_channel_name, fallback=f"ticket-{next_num:04d}")

        # Build permission overwrites
        overwrites: Dict[Any, Any] = {}
        if getattr(guild, "default_role", None) is not None:
            overwrites[guild.default_role] = discord.PermissionOverwrite(
                view_channel=False,
                send_messages=False,
                read_message_history=False,
            )
        overwrites[creator] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
        )
        if getattr(guild, "me", None) is not None:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
                attach_files=True,
                embed_links=True,
            )

        staff_role_ids = json.loads(cat_cfg.get("staff_role_ids_json") or "[]")
        for rid in staff_role_ids:
            role_obj = guild.get_role(int(rid)) if hasattr(guild, "get_role") else None
            if role_obj is not None:
                overwrites[role_obj] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                )

        discord_category = None
        if cat_cfg.get("discord_category_id") and hasattr(guild, "get_channel"):
            discord_category = guild.get_channel(int(cat_cfg["discord_category_id"]))

        channel = await guild.create_text_channel(
            name=channel_name,
            category=discord_category,
            overwrites=overwrites,
            reason=f"Cosmic ki baddie Ticket #{next_num:04d} ({cat_cfg['display_name']}) opened by {creator.name}",
        )

        responses_payload = form_responses or {}
        ticket_id = await self.db.execute(
            """
            INSERT INTO tickets (
                guild_id, ticket_number, channel_id, creator_id, category_key,
                status, form_responses_json, created_at
            ) VALUES (?, ?, ?, ?, ?, 'open', ?, datetime('now'));
            """,
            (
                guild_id,
                next_num,
                int(channel.id),
                creator_id,
                category_key,
                json.dumps(responses_payload),
            ),
        )

        record = await self.get_ticket_by_id(ticket_id)
        return True, f"Ticket `#{next_num:04d}` created in <#{channel.id}>.", record, channel

    async def get_ticket_by_id(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        return await self.db.fetch_one("SELECT * FROM tickets WHERE ticket_id = ?;", (ticket_id,))

    async def get_ticket_by_channel(self, channel_id: int) -> Optional[Dict[str, Any]]:
        return await self.db.fetch_one(
            "SELECT * FROM tickets WHERE channel_id = ? ORDER BY ticket_id DESC LIMIT 1;",
            (int(channel_id),),
        )

    async def claim_ticket(self, channel_id: int, moderator_id: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        ticket = await self.get_ticket_by_channel(channel_id)
        if not ticket:
            return False, "This channel is not an active ticket channel.", None
        if ticket["status"] == "closed":
            return False, "Cannot claim a closed ticket.", None
        if ticket.get("claimed_by_id") == int(moderator_id):
            return False, "You have already claimed this ticket.", ticket

        await self.db.execute(
            "UPDATE tickets SET claimed_by_id = ?, status = 'claimed' WHERE ticket_id = ?;",
            (int(moderator_id), int(ticket["ticket_id"])),
        )
        updated = await self.get_ticket_by_id(int(ticket["ticket_id"]))
        return True, f"Ticket `#{ticket['ticket_number']:04d}` claimed by <@{moderator_id}>.", updated

    async def unclaim_ticket(self, channel_id: int, actor_id: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        ticket = await self.get_ticket_by_channel(channel_id)
        if not ticket:
            return False, "This channel is not an active ticket channel.", None
        if not ticket.get("claimed_by_id"):
            return False, "This ticket is not currently claimed.", ticket

        await self.db.execute(
            "UPDATE tickets SET claimed_by_id = NULL, status = 'open' WHERE ticket_id = ?;",
            (int(ticket["ticket_id"]),),
        )
        updated = await self.get_ticket_by_id(int(ticket["ticket_id"]))
        return True, f"Ticket `#{ticket['ticket_number']:04d}` is now unclaimed.", updated

    async def transfer_ticket(self, channel_id: int, new_staff_id: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        ticket = await self.get_ticket_by_channel(channel_id)
        if not ticket:
            return False, "This channel is not an active ticket channel.", None
        await self.db.execute(
            "UPDATE tickets SET claimed_by_id = ?, status = 'claimed' WHERE ticket_id = ?;",
            (int(new_staff_id), int(ticket["ticket_id"])),
        )
        updated = await self.get_ticket_by_id(int(ticket["ticket_id"]))
        return True, f"Ticket `#{ticket['ticket_number']:04d}` transferred to <@{new_staff_id}>.", updated

    async def generate_transcript(
        self,
        guild: Any,
        channel: Any,
        ticket: Dict[str, Any],
        closing_moderator: Any,
        close_reason: str,
    ) -> str:
        """Build a complete, human-readable transcript including metadata, form answers, and message log."""
        cat_cfg = await self.get_category_config(int(guild.id), ticket["category_key"])
        cat_name = cat_cfg["display_name"] if cat_cfg else ticket["category_key"]
        claimed_id = ticket.get("claimed_by_id")
        effective_mod_id = claimed_id if claimed_id else int(closing_moderator.id)

        lines: List[str] = [
            "================================================================================",
            f"COSMIC KI BADDIE (AURORA) — OFFICIAL TICKET TRANSCRIPT #{ticket['ticket_number']:04d}",
            "================================================================================",
            f"Server:           {getattr(guild, 'name', 'Server')} ({guild.id})",
            f"Ticket ID:        #{ticket['ticket_number']:04d} (DB ID: {ticket['ticket_id']})",
            f"Category:         {cat_name} ({ticket['category_key']})",
            f"Ticket Creator:   User ID {ticket['creator_id']}",
            f"Claimed By:       {f'User ID {claimed_id}' if claimed_id else 'Unclaimed (Handled by closer)'}",
            f"Closed By:        {getattr(closing_moderator, 'name', 'Moderator')} (User ID {closing_moderator.id})",
            f"Notified Staff:   User ID {effective_mod_id}",
            f"Closing Reason:   {close_reason}",
            f"Created At:       {ticket.get('created_at', 'N/A')}",
            f"Closed At:        {utc_now_iso()}",
            "--------------------------------------------------------------------------------",
            "SUBMITTED FORM RESPONSES:",
        ]

        form_data = json.loads(ticket.get("form_responses_json") or "{}")
        if form_data:
            for k, v in form_data.items():
                lines.append(f"  • {k}: {v}")
        else:
            lines.append("  (No custom form fields submitted)")

        lines.append("--------------------------------------------------------------------------------")
        lines.append("CHANNEL MESSAGE HISTORY:")

        messages_logged = 0
        if channel is not None and hasattr(channel, "history"):
            try:
                hist = await channel.history(limit=250)
                if isinstance(hist, list):
                    msg_list = hist
                else:
                    msg_list = [m async for m in hist]
                for msg in msg_list:
                    author_name = getattr(getattr(msg, "author", None), "name", "User")
                    content = getattr(msg, "content", "") or "[Embed/Attachment]"
                    ts = getattr(msg, "created_at", None)
                    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else ""
                    lines.append(f"[{ts_str}] {author_name}: {content}")
                    messages_logged += 1
            except Exception as exc:
                lines.append(f"[Note: Could not fetch full channel history: {exc}]")

        if messages_logged == 0:
            lines.append("[No text messages recorded prior to closure]")

        lines.append("================================================================================")
        return "\n".join(lines)

    async def close_ticket(
        self,
        guild: Any,
        channel: Any,
        closing_moderator: Any,
        reason: str = "Resolved by staff",
        schedule_delete: bool = False,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Execute the mandatory 8-step Ticket Closing Pipeline:
        1. Generate complete transcript.
        2. Save transcript in configured transcript channel (category-specific or guild-default).
        3. DM the ticket creator.
        4. DM the moderator who claimed the ticket.
        5. Include ticket ID, creator, moderator, category, closing reason, and transcript.
        6. If no moderator claimed the ticket, notify the moderator who closed it instead.
        7. Handle failed DMs gracefully without raising unhandled errors.
        8. Keep the ticket channel until the configured deletion period expires.
        """
        ticket = await self.get_ticket_by_channel(int(channel.id))
        if not ticket:
            return False, "This channel is not a registered ticket.", None
        if ticket["status"] == "closed":
            return False, "This ticket is already closed.", ticket

        guild_id = int(guild.id)
        cat_cfg = await self.get_category_config(guild_id, ticket["category_key"])
        cat_name = cat_cfg["display_name"] if cat_cfg else ticket["category_key"]

        transcript_text = await self.generate_transcript(
            guild=guild,
            channel=channel,
            ticket=ticket,
            closing_moderator=closing_moderator,
            close_reason=reason,
        )

        claimed_by_id = ticket.get("claimed_by_id")
        target_staff_id = int(claimed_by_id) if claimed_by_id else int(closing_moderator.id)

        # Build summary embed shared across transcript channel, creator DM, and staff DM
        summary_embed = discord.Embed(
            title=f"Ticket Closed — #{ticket['ticket_number']:04d}",
            description=f"Your ticket in **{getattr(guild, 'name', 'Server')}** has been closed and archived.",
            color=discord.Color.blurple(),
        )
        summary_embed.add_field(name="Ticket ID", value=f"`#{ticket['ticket_number']:04d}`", inline=True)
        summary_embed.add_field(name="Creator", value=f"<@{ticket['creator_id']}> (`{ticket['creator_id']}`)", inline=True)
        summary_embed.add_field(
            name="Moderator",
            value=f"<@{target_staff_id}> (`{target_staff_id}`)",
            inline=True,
        )
        summary_embed.add_field(name="Category", value=cat_name, inline=True)
        summary_embed.add_field(name="Closing Reason", value=reason, inline=False)
        summary_embed.set_footer(text=f"Closed at {utc_now_iso()} · Cosmic ki baddie Ticket System")

        # Step 2: Save transcript in configured transcript channel
        transcript_ch_id = (cat_cfg or {}).get("transcript_channel_id")
        if not transcript_ch_id:
            g_cfg = await self.db.fetch_one(
                "SELECT transcript_channel_id FROM guild_configs WHERE guild_id = ?;",
                (guild_id,),
            )
            transcript_ch_id = (g_cfg or {}).get("transcript_channel_id")

        if transcript_ch_id and hasattr(guild, "get_channel"):
            t_channel = guild.get_channel(int(transcript_ch_id))
            if t_channel and hasattr(t_channel, "send"):
                try:
                    t_file = discord.File(
                        io.BytesIO(transcript_text.encode("utf-8")),
                        filename=f"ticket-{ticket['ticket_number']:04d}-transcript.txt",
                    )
                    await t_channel.send(embed=summary_embed, file=t_file)
                except Exception as exc:
                    logger.warning("Failed to post transcript to channel %s: %s", transcript_ch_id, exc)

        # Step 3 & 7: DM the ticket creator (graceful fallback if DMs closed)
        dm_creator_sent = 0
        creator_member = guild.get_member(int(ticket["creator_id"])) if hasattr(guild, "get_member") else None
        if creator_member is not None and hasattr(creator_member, "send"):
            try:
                creator_file = discord.File(
                    io.BytesIO(transcript_text.encode("utf-8")),
                    filename=f"ticket-{ticket['ticket_number']:04d}-transcript.txt",
                )
                await creator_member.send(embed=summary_embed, file=creator_file)
                dm_creator_sent = 1
            except Exception as exc:
                logger.info("Creator DM could not be delivered for ticket #%d: %s", ticket["ticket_number"], exc)

        # Step 4, 6 & 7: DM the moderator who claimed the ticket (or closing moderator if unclaimed)
        dm_staff_sent = 0
        staff_member = (
            guild.get_member(target_staff_id)
            if hasattr(guild, "get_member")
            else None
        ) or (closing_moderator if int(closing_moderator.id) == target_staff_id else None)

        if staff_member is not None and hasattr(staff_member, "send"):
            try:
                staff_file = discord.File(
                    io.BytesIO(transcript_text.encode("utf-8")),
                    filename=f"ticket-{ticket['ticket_number']:04d}-transcript.txt",
                )
                await staff_member.send(embed=summary_embed, file=staff_file)
                dm_staff_sent = 1
            except Exception as exc:
                logger.info("Staff DM could not be delivered for ticket #%d: %s", ticket["ticket_number"], exc)

        # Persist closed state & transcript in SQLite
        await self.db.execute(
            """
            UPDATE tickets SET
                status = 'closed',
                closed_by_id = ?,
                close_reason = ?,
                transcript_text = ?,
                dm_creator_sent = ?,
                dm_staff_sent = ?,
                closed_at = datetime('now')
            WHERE ticket_id = ?;
            """,
            (
                int(closing_moderator.id),
                reason,
                transcript_text,
                dm_creator_sent,
                dm_staff_sent,
                int(ticket["ticket_id"]),
            ),
        )

        # Step 8: Lock channel for creator and retain channel until configured deletion period expires
        auto_delete_sec = int((cat_cfg or {}).get("auto_delete_seconds") or 300)
        if creator_member is not None and hasattr(channel, "set_permissions"):
            try:
                await channel.set_permissions(
                    creator_member,
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True,
                )
            except Exception:
                pass

        if schedule_delete and auto_delete_sec > 0 and hasattr(channel, "delete"):
            async def _delayed_delete() -> None:
                await asyncio.sleep(auto_delete_sec)
                try:
                    await channel.delete(reason=f"Ticket #{ticket['ticket_number']:04d} retention period expired")
                except Exception:
                    pass

            asyncio.create_task(_delayed_delete())

        updated = await self.get_ticket_by_id(int(ticket["ticket_id"]))
        status_note = (
            f"Ticket `#{ticket['ticket_number']:04d}` closed. "
            f"Creator DM: {'Sent' if dm_creator_sent else 'Unavailable (DMs Closed)'} · "
            f"Staff DM (<@{target_staff_id}>): {'Sent' if dm_staff_sent else 'Unavailable (DMs Closed)'} · "
            f"Channel retained for {auto_delete_sec}s before cleanup."
        )
        return True, status_note, updated

    async def reopen_ticket(self, guild: Any, channel: Any) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        ticket = await self.get_ticket_by_channel(int(channel.id))
        if not ticket:
            return False, "This channel is not a registered ticket.", None
        if ticket["status"] != "closed":
            return False, "Only closed tickets can be reopened.", ticket

        await self.db.execute(
            "UPDATE tickets SET status = 'open', closed_at = NULL WHERE ticket_id = ?;",
            (int(ticket["ticket_id"]),),
        )
        creator = guild.get_member(int(ticket["creator_id"])) if hasattr(guild, "get_member") else None
        if creator is not None and hasattr(channel, "set_permissions"):
            try:
                await channel.set_permissions(
                    creator,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )
            except Exception:
                pass

        updated = await self.get_ticket_by_id(int(ticket["ticket_id"]))
        return True, f"Ticket `#{ticket['ticket_number']:04d}` has been reopened.", updated

    async def get_ticket_statistics(self, guild_id: int) -> Dict[str, Any]:
        total_row = await self.db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM tickets WHERE guild_id = ?;",
            (guild_id,),
        )
        open_row = await self.db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM tickets WHERE guild_id = ? AND status IN ('open', 'claimed');",
            (guild_id,),
        )
        claimed_row = await self.db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM tickets WHERE guild_id = ? AND status = 'claimed';",
            (guild_id,),
        )
        closed_row = await self.db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM tickets WHERE guild_id = ? AND status = 'closed';",
            (guild_id,),
        )
        by_cat = await self.db.fetch_all(
            "SELECT category_key, COUNT(*) AS count FROM tickets WHERE guild_id = ? GROUP BY category_key;",
            (guild_id,),
        )
        return {
            "total": int((total_row or {}).get("cnt", 0)),
            "open": int((open_row or {}).get("cnt", 0)),
            "claimed": int((claimed_row or {}).get("cnt", 0)),
            "closed": int((closed_row or {}).get("cnt", 0)),
            "by_category": {r["category_key"]: int(r["count"]) for r in by_cat},
        }
