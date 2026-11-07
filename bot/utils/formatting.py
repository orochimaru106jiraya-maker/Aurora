"""
Formatting utilities for Cosmic ki baddie.
Handles duration strings, transcript formatting, channel name slugs, and timestamps.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

DURATION_REGEX = re.compile(r"^\s*(?:(\d+)\s*d)?\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+)\s*s)?\s*$", re.IGNORECASE)


def parse_duration_seconds(raw: Optional[str]) -> Optional[int]:
    """
    Parse human-readable duration strings such as '10m', '2h30m', '7d', '45s' into seconds.
    Returns None if raw is empty or invalid.
    """
    if not raw or not raw.strip():
        return None
    clean = raw.strip()
    if clean.isdigit():
        return int(clean)
    match = DURATION_REGEX.match(clean)
    if not match or not any(match.groups()):
        return None
    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = int(match.group(4) or 0)
    total = days * 86400 + hours * 3600 + minutes * 60 + seconds
    return total if total > 0 else None


def format_duration(seconds: Optional[int]) -> str:
    """Format seconds into a concise string like '2h 15m' or 'Permanent'."""
    if seconds is None or seconds <= 0:
        return "Permanent"
    rem = int(seconds)
    days, rem = divmod(rem, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs:
        parts.append(f"{secs}s")
    return " ".join(parts) if parts else "0s"


def sanitize_channel_name(raw_name: str, fallback: str = "ticket") -> str:
    """Sanitize a string into a valid Discord text channel slug (lowercase alphanumeric and hyphens)."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw_name.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return (slug[:95] if slug else fallback)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
