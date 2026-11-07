"""
Slash command decorators and centralized server-side permission checks for Cosmic ki baddie.
Every command and interactive UI control validates permissions through PermissionService.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from bot.core.discord_compat import app_commands, discord
from bot.core.error_handler import RBACPermissionDeniedError
from bot.database.models import PermissionLevel

T = TypeVar("T")


def require_permission_level(
    level: PermissionLevel,
    module_name: str = "general",
) -> Callable[[T], T]:
    """
    Decorator for Slash Commands that enforces server-side RBAC + Discord native permissions
    via `bot.permission_service.check_interaction_permission`.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        bot = getattr(interaction, "client", None)
        if bot is None or not hasattr(bot, "permission_service"):
            # Fallback to Discord native administrator check if service unavailable
            user_perms = getattr(interaction.user, "guild_permissions", None)
            if user_perms and getattr(user_perms, "administrator", False):
                return True
            raise RBACPermissionDeniedError("Permission service is not initialized.")

        command_name = getattr(getattr(interaction, "command", None), "qualified_name", "unknown")
        allowed, reason = await bot.permission_service.authorize_interaction(
            interaction=interaction,
            command_name=command_name,
            module_name=module_name,
            default_level=level,
        )
        if not allowed:
            raise RBACPermissionDeniedError(reason)
        return True

    return app_commands.check(predicate)
