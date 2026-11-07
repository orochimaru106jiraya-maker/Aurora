"""
Confirmation Dialog Views for Cosmic ki baddie.
Used for destructive or high-impact actions (e.g., /ban, /clearwarnings, /clearcases, /permissions reset, /jticket delete).
"""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

from bot.core.discord_compat import discord


class ConfirmationView(discord.ui.View):
    """Interactive Confirm / Cancel view with author verification."""

    def __init__(
        self,
        author_id: int,
        on_confirm: Callable[[discord.Interaction], Awaitable[None]],
        confirm_label: str = "Confirm Action",
        cancel_label: str = "Cancel",
        timeout: float = 60.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.author_id = int(author_id)
        self.on_confirm_callback = on_confirm
        self.confirmed: Optional[bool] = None

        confirm_btn = discord.ui.Button(
            label=confirm_label,
            style=discord.ButtonStyle.danger,
            custom_id="cosmic:confirm:accept",
        )
        cancel_btn = discord.ui.Button(
            label=cancel_label,
            style=discord.ButtonStyle.secondary,
            custom_id="cosmic:confirm:cancel",
        )
        confirm_btn.callback = self._handle_confirm
        cancel_btn.callback = self._handle_cancel
        self.add_item(confirm_btn)
        self.add_item(cancel_btn)

    async def _handle_confirm(self, interaction: discord.Interaction) -> None:
        if int(interaction.user.id) != self.author_id:
            await interaction.response.send_message(
                "Only the user who initiated this command can confirm it.",
                ephemeral=True,
            )
            return
        self.confirmed = True
        self.stop()
        await self.on_confirm_callback(interaction)

    async def _handle_cancel(self, interaction: discord.Interaction) -> None:
        if int(interaction.user.id) != self.author_id:
            await interaction.response.send_message(
                "Only the user who initiated this command can cancel it.",
                ephemeral=True,
            )
            return
        self.confirmed = False
        self.stop()
        embed = discord.Embed(
            title="Action Cancelled",
            description="The requested operation was cancelled safely.",
            color=discord.Color.dark_theme(),
        )
        await interaction.response.edit_message(embed=embed, view=None)
