"""
Centralized Error Handler for Cosmic ki baddie.
Handles app_commands (Slash Command) errors, permission denials, hierarchy violations,
rate limits, and unexpected exceptions with clean ephemeral user feedback.
"""

from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING

from bot.core.discord_compat import app_commands, discord

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot

logger = logging.getLogger("cosmic.core.error_handler")


class HierarchyViolationError(app_commands.CheckFailure):
    """Raised when a moderator attempts to target a member with equal or higher role hierarchy."""


class RBACPermissionDeniedError(app_commands.CheckFailure):
    """Raised when a user lacks the required RBAC role or permission level."""


class PrivilegeEscalationError(app_commands.CheckFailure):
    """Raised when a user attempts to grant permissions equal to or higher than their own."""


def register_error_handlers(bot: "CosmicBot") -> None:
    """Attach global tree error handler to the bot."""

    @bot.tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: Exception) -> None:
        cmd_name = getattr(getattr(interaction, "command", None), "qualified_name", "unknown")

        if isinstance(error, (RBACPermissionDeniedError, HierarchyViolationError, PrivilegeEscalationError)):
            embed = discord.Embed(
                title="Access Denied",
                description=str(error),
                color=discord.Color.red(),
            )
            embed.set_footer(text=f"Command: /{cmd_name} · Cosmic ki baddie RBAC Guard")
        elif isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="Permission Required",
                description=str(error) or "You do not have permission to execute this command.",
                color=discord.Color.red(),
            )
            embed.set_footer(text=f"Command: /{cmd_name}")
        elif isinstance(error, discord.Forbidden):
            embed = discord.Embed(
                title="Missing Discord Bot Permissions",
                description=(
                    "Cosmic ki baddie is missing required Discord role/channel permissions to complete this action. "
                    "Please check that the bot's role is positioned above target roles and has the necessary permissions."
                ),
                color=discord.Color.red(),
            )
        else:
            logger.error(
                "Unhandled error in slash command /%s invoked by %s: %s\n%s",
                cmd_name,
                getattr(interaction.user, "id", "unknown"),
                error,
                traceback.format_exc(),
            )
            embed = discord.Embed(
                title="Command Execution Error",
                description=f"An error occurred while executing `/{cmd_name}`: `{type(error).__name__}: {error}`",
                color=discord.Color.red(),
            )

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as send_exc:
            logger.warning("Could not deliver error response for /%s: %s", cmd_name, send_exc)
