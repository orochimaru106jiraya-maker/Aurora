"""
Input validation and security checks for Cosmic ki baddie.
Validates hex colors, URLs, role hierarchy rules, and embed limits.
"""

from __future__ import annotations

import re
from typing import Any, Optional, Tuple
from urllib.parse import urlparse

HEX_COLOR_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def validate_hex_color(value: str) -> Tuple[bool, int]:
    """Validate a 6-digit hex color string and return (is_valid, integer_color)."""
    clean = value.strip()
    if not HEX_COLOR_RE.match(clean):
        return False, 0x6366F1
    hex_digits = clean.lstrip("#")
    return True, int(hex_digits, 16)


def is_valid_http_url(url: str) -> bool:
    """Validate that a string is a properly formed http/https URL."""
    if not url or not url.strip():
        return False
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def validate_role_hierarchy(
    actor: Any,
    target: Any,
    guild: Any,
    bot_owner_id: Optional[int] = None,
) -> Tuple[bool, str]:
    """
    Enforce strict Discord role hierarchy protection:
    1. No moderator can act against the Server Owner.
    2. No moderator can act against the Bot Owner.
    3. No moderator can act against themselves.
    4. Unless the actor is the Server Owner, the actor's top_role must be strictly higher than target's top_role.
    5. The bot's own top_role must be strictly higher than the target's top_role.
    """
    if getattr(actor, "id", None) == getattr(target, "id", None):
        return False, "You cannot perform this moderation action on yourself."

    if guild is not None and getattr(target, "id", None) == getattr(guild, "owner_id", None):
        return False, "Hierarchy Protection: You cannot perform moderation actions against the Server Owner."

    if bot_owner_id and getattr(target, "id", None) == bot_owner_id:
        return False, "Hierarchy Protection: You cannot perform moderation actions against the Bot Owner."

    is_actor_server_owner = guild is not None and getattr(actor, "id", None) == getattr(guild, "owner_id", None)
    actor_top = getattr(actor, "top_role", None)
    target_top = getattr(target, "top_role", None)

    if not is_actor_server_owner and actor_top is not None and target_top is not None:
        if actor_top.position <= target_top.position:
            return (
                False,
                f"Hierarchy Protection: Target member's highest role ({target_top.name}) is equal to or higher than your highest role ({actor_top.name}).",
            )

    bot_member = getattr(guild, "me", None) if guild is not None else None
    bot_top = getattr(bot_member, "top_role", None) if bot_member is not None else None
    if bot_top is not None and target_top is not None:
        if bot_top.position <= target_top.position:
            return (
                False,
                f"Bot Hierarchy Protection: Target member's highest role ({target_top.name}) is equal to or higher than Cosmic ki baddie's highest role ({bot_top.name}).",
            )

    return True, "Hierarchy check passed."


def validate_assignable_role(role: Any, guild: Any) -> Tuple[bool, str]:
    """Ensure a role can be safely assigned by the bot (below bot's highest role and not @everyone)."""
    if guild is not None and getattr(role, "id", None) == getattr(guild, "id", None):
        return False, "Cannot assign the @everyone default role."
    bot_member = getattr(guild, "me", None) if guild is not None else None
    bot_top = getattr(bot_member, "top_role", None) if bot_member is not None else None
    if bot_top is not None and getattr(role, "position", 0) >= bot_top.position:
        return (
            False,
            f"Role Hierarchy Protection: Role {getattr(role, 'name', role)} is equal to or above the bot's highest role ({bot_top.name}).",
        )
    return True, "Role is assignable."
