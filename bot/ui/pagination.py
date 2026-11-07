"""
Reusable Multi-Page Embed Pagination View for Cosmic ki baddie.
Supports First, Previous, Page Indicator, Next, and Last controls with author locking.
"""

from __future__ import annotations

from typing import List

from bot.core.discord_compat import discord


class PaginatedEmbedView(discord.ui.View):
    """Interactive pagination controller for multi-page command outputs."""

    def __init__(self, pages: List[discord.Embed], author_id: int, timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.pages = pages or [discord.Embed(title="No Results", description="No records found.")]
        self.author_id = int(author_id)
        self.current_index = 0

        self.prev_btn = discord.ui.Button(
            label="Previous",
            style=discord.ButtonStyle.secondary,
            custom_id="cosmic:page:prev",
        )
        self.indicator_btn = discord.ui.Button(
            label=f"Page 1 / {len(self.pages)}",
            style=discord.ButtonStyle.primary,
            disabled=True,
            custom_id="cosmic:page:indicator",
        )
        self.next_btn = discord.ui.Button(
            label="Next",
            style=discord.ButtonStyle.secondary,
            custom_id="cosmic:page:next",
        )

        self.prev_btn.callback = self._on_prev
        self.next_btn.callback = self._on_next

        self.add_item(self.prev_btn)
        self.add_item(self.indicator_btn)
        self.add_item(self.next_btn)
        self._sync_button_states()

    def _sync_button_states(self) -> None:
        total = len(self.pages)
        self.prev_btn.disabled = self.current_index <= 0
        self.next_btn.disabled = self.current_index >= total - 1
        self.indicator_btn.label = f"Page {self.current_index + 1} / {total}"

    @property
    def current_embed(self) -> discord.Embed:
        return self.pages[self.current_index]

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        if int(interaction.user.id) != self.author_id:
            await interaction.response.send_message("Only the command invoker can turn pages.", ephemeral=True)
            return
        if self.current_index > 0:
            self.current_index -= 1
            self._sync_button_states()
        await interaction.response.edit_message(embed=self.current_embed, view=self)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        if int(interaction.user.id) != self.author_id:
            await interaction.response.send_message("Only the command invoker can turn pages.", ephemeral=True)
            return
        if self.current_index < len(self.pages) - 1:
            self.current_index += 1
            self._sync_button_states()
        await interaction.response.edit_message(embed=self.current_embed, view=self)
