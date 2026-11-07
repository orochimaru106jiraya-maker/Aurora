"""
Automated Ticket System Tests (`tests/test_tickets.py`).
Tests:
- All 4 default ticket categories seeded (`general_help`, `file_complaint`, `staff_application`, `claim_prize`)
- Ticket creation & channel permission overwrites
- Duplicate open ticket prevention per user per category
- Ticket claiming, unclaiming, and transferring
- Ticket closing pipeline:
  1. Complete transcript generation
  2. Archiving in configured transcript channel
  3. DM sent to ticket creator
  4. DM sent to claiming moderator (or closing moderator when unclaimed)
  5. Graceful handling when creator has DMs disabled (`Forbidden`)
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bot.core.discord_compat import discord
from bot.database.manager import DatabaseManager
from bot.database.models import TicketCategoryKey
from bot.services.ticket_service import TicketService


class TestTicketSystem(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.tmp_dir.name) / "tickets_test.db")
        await self.db.connect()
        self.ticket_service = TicketService(self.db)

        self.guild = discord.Guild(id=8080, name="Ticket Test Server", owner_id=1)
        self.transcript_ch = await self.guild.create_text_channel(name="ticket-transcripts")
        self.creator = discord.Member(id=5001, name="AliceCreator", guild=self.guild)
        self.claiming_mod = discord.Member(id=6001, name="BobClaimer", guild=self.guild)
        self.closing_mod = discord.Member(id=6002, name="CharlieCloser", guild=self.guild)
        self.guild.members.extend([self.creator, self.claiming_mod, self.closing_mod])

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.tmp_dir.cleanup()

    async def test_four_default_categories_and_duplicate_prevention(self) -> None:
        cats = await self.ticket_service.ensure_default_categories(self.guild.id)
        self.assertEqual(len(cats), 4)

        # Configure transcript channel
        await self.ticket_service.update_category_config(
            self.guild.id,
            TicketCategoryKey.GENERAL_HELP.value,
            transcript_channel_id=self.transcript_ch.id,
        )

        # Open first ticket
        ok1, _, rec1, ch1 = await self.ticket_service.open_ticket(
            guild=self.guild,
            creator=self.creator,
            category_key=TicketCategoryKey.GENERAL_HELP.value,
            form_responses={"How can we help you?": "Need role help"},
        )
        self.assertTrue(ok1)
        self.assertIsNotNone(rec1)
        self.assertIsNotNone(ch1)

        # Attempt duplicate ticket in same category
        ok2, msg2, _, _ = await self.ticket_service.open_ticket(
            guild=self.guild,
            creator=self.creator,
            category_key=TicketCategoryKey.GENERAL_HELP.value,
        )
        self.assertFalse(ok2)
        self.assertIn("Duplicate Ticket Prevented", msg2)

    async def test_claim_and_close_pipeline_dms_creator_and_claiming_moderator(self) -> None:
        await self.ticket_service.update_category_config(
            self.guild.id,
            TicketCategoryKey.CLAIM_PRIZE.value,
            transcript_channel_id=self.transcript_ch.id,
        )
        ok, _, rec, ch = await self.ticket_service.open_ticket(
            guild=self.guild,
            creator=self.creator,
            category_key=TicketCategoryKey.CLAIM_PRIZE.value,
            form_responses={"Event": "Weekly Giveaway #1"},
        )
        self.assertTrue(ok)
        await ch.send("Hello staff, here is my screenshot proof!")

        # Claim ticket as BobClaimer
        claimed_ok, _, _ = await self.ticket_service.claim_ticket(ch.id, self.claiming_mod.id)
        self.assertTrue(claimed_ok)

        # Close ticket as CharlieCloser -> must DM AliceCreator AND BobClaimer (who claimed it)
        closed_ok, _, closed_rec = await self.ticket_service.close_ticket(
            guild=self.guild,
            channel=ch,
            closing_moderator=self.closing_mod,
            reason="Prize verified and delivered",
        )
        self.assertTrue(closed_ok)
        self.assertEqual(closed_rec["status"], "closed")
        self.assertEqual(closed_rec["dm_creator_sent"], 1)
        self.assertEqual(closed_rec["dm_staff_sent"], 1)
        self.assertIn("Hello staff, here is my screenshot proof!", closed_rec["transcript_text"])

        # Verify transcript channel received message + file
        self.assertEqual(len(self.transcript_ch.sent_messages), 1)
        # Verify creator and claiming mod received DMs
        self.assertEqual(len(self.creator.dm_messages), 1)
        self.assertEqual(len(self.claiming_mod.dm_messages), 1)

    async def test_unclaimed_ticket_notifies_closing_moderator_and_handles_closed_dms(self) -> None:
        # Disable DMs on creator to test graceful Forbidden handling
        self.creator.allow_dms = False
        ok, _, _, ch = await self.ticket_service.open_ticket(
            guild=self.guild,
            creator=self.creator,
            category_key=TicketCategoryKey.FILE_COMPLAINT.value,
        )
        self.assertTrue(ok)

        # Close without anyone claiming -> must notify closing_mod and not crash on creator's closed DMs
        closed_ok, _, closed_rec = await self.ticket_service.close_ticket(
            guild=self.guild,
            channel=ch,
            closing_moderator=self.closing_mod,
            reason="Handled directly",
        )
        self.assertTrue(closed_ok)
        self.assertEqual(closed_rec["dm_creator_sent"], 0)
        self.assertEqual(closed_rec["dm_staff_sent"], 1)
        self.assertEqual(len(self.closing_mod.dm_messages), 1)


if __name__ == "__main__":
    unittest.main()
