"""
Database domain models and typed data structures for Cosmic ki baddie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TicketCategoryKey(str, Enum):
    GENERAL_HELP = "general_help"
    FILE_COMPLAINT = "file_complaint"
    STAFF_APPLICATION = "staff_application"
    CLAIM_PRIZE = "claim_prize"


DEFAULT_TICKET_CATEGORIES: Dict[str, Dict[str, Any]] = {
    TicketCategoryKey.GENERAL_HELP.value: {
        "key": TicketCategoryKey.GENERAL_HELP.value,
        "name": "General Help",
        "emoji": "🛟",
        "description": "Get assistance with server rules, channels, roles, or general questions.",
        "naming_format": "help-{username}-{id}",
        "max_open_per_user": 1,
        "auto_delete_delay_seconds": 300,
        "form_fields": [
            {"label": "How can we help you?", "placeholder": "Describe your issue in detail...", "required": True, "style": "paragraph"},
            {"label": "Relevant Channel or User", "placeholder": "#general or @username (optional)", "required": False, "style": "short"},
        ],
    },
    TicketCategoryKey.FILE_COMPLAINT.value: {
        "key": TicketCategoryKey.FILE_COMPLAINT.value,
        "name": "File a Complaint",
        "emoji": "⚖️",
        "description": "Report rule violations, harassment, or staff misconduct confidentially.",
        "naming_format": "complaint-{username}-{id}",
        "max_open_per_user": 1,
        "auto_delete_delay_seconds": 600,
        "form_fields": [
            {"label": "Reported User(s) & ID", "placeholder": "Username / User ID", "required": True, "style": "short"},
            {"label": "Incident Description & Evidence", "placeholder": "Provide timestamps, links, and context...", "required": True, "style": "paragraph"},
        ],
    },
    TicketCategoryKey.STAFF_APPLICATION.value: {
        "key": TicketCategoryKey.STAFF_APPLICATION.value,
        "name": "Apply for a Staff Role",
        "emoji": "🛡️",
        "description": "Submit an application to join our moderation or support team.",
        "naming_format": "apply-{username}-{id}",
        "max_open_per_user": 1,
        "auto_delete_delay_seconds": 600,
        "form_fields": [
            {"label": "Desired Role & Timezone", "placeholder": "e.g., Moderator / UTC-5", "required": True, "style": "short"},
            {"label": "Previous Moderation Experience", "placeholder": "List servers, sizes, and responsibilities...", "required": True, "style": "paragraph"},
            {"label": "Weekly Availability (Hours)", "placeholder": "e.g., 15-20 hours/week", "required": True, "style": "short"},
        ],
    },
    TicketCategoryKey.CLAIM_PRIZE.value: {
        "key": TicketCategoryKey.CLAIM_PRIZE.value,
        "name": "Claim Winning Prize",
        "emoji": "🏆",
        "description": "Verify and claim rewards from server giveaways, events, or tournaments.",
        "naming_format": "prize-{username}-{id}",
        "max_open_per_user": 1,
        "auto_delete_delay_seconds": 300,
        "form_fields": [
            {"label": "Event or Giveaway Name", "placeholder": "e.g., Weekly Nitro Giveaway #14", "required": True, "style": "short"},
            {"label": "Winning Message Link / Proof", "placeholder": "Paste message link or details...", "required": True, "style": "paragraph"},
        ],
    },
}


class PermissionLevel(str, Enum):
    EVERYONE = "everyone"
    DJ = "music_dj"
    TICKET_STAFF = "ticket_staff"
    SUPPORT = "support_team"
    MODERATOR = "moderator"
    ADMIN = "administrator"
    SERVER_OWNER = "server_owner"
    BOT_OWNER = "bot_owner"


PERMISSION_HIERARCHY: Dict[str, int] = {
    PermissionLevel.EVERYONE.value: 0,
    PermissionLevel.DJ.value: 10,
    PermissionLevel.TICKET_STAFF.value: 20,
    PermissionLevel.SUPPORT.value: 30,
    PermissionLevel.MODERATOR.value: 50,
    PermissionLevel.ADMIN.value: 80,
    PermissionLevel.SERVER_OWNER.value: 90,
    PermissionLevel.BOT_OWNER.value: 100,
}


@dataclass
class GuildConfigModel:
    guild_id: int
    prefix: str = "!"
    mod_log_channel_id: Optional[int] = None
    server_log_channel_id: Optional[int] = None
    transcript_channel_id: Optional[int] = None
    snipe_Retention_limit: int = 20
    enabled_modules: Dict[str, bool] = field(default_factory=lambda: {
        "moderation": True,
        "tickets": True,
        "permissions": True,
        "activity_roles": True,
        "reaction_roles": True,
        "jtc": True,
        "music": True,
        "ai_assistant": True,
        "auto_responder": True,
        "embeds": True,
        "administration": True,
    })
    updated_at: str = ""


@dataclass
class TicketRecord:
    ticket_id: int
    guild_id: int
    channel_id: int
    creator_id: int
    category_key: str
    status: str  # "open", "claimed", "closed", "deleted"
    claimed_by_id: Optional[int] = None
    closed_by_id: Optional[int] = None
    close_reason: Optional[str] = None
    form_responses_json: str = "{}"
    transcript_text: Optional[str] = None
    created_at: str = ""
    closed_at: Optional[str] = None


@dataclass
class ModerationCase:
    case_id: int
    guild_id: int
    case_number: int
    action_type: str  # ban, unban, kick, timeout, untimeout, warn, lock, unlock, slowmode, purge
    target_user_id: int
    moderator_id: int
    reason: str
    duration_seconds: Optional[int] = None
    active: bool = True
    created_at: str = ""
