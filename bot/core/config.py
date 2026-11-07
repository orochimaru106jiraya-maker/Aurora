"""
Environment configuration and structured logging setup for Cosmic ki baddie.
Never hardcodes bot tokens or secrets.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except ImportError:
    pass


@dataclass
class BotConfig:
    discord_token: str
    application_id: Optional[int]
    test_guild_id: Optional[int]
    database_path: str
    bot_owner_id: int
    default_prefix: str
    local_llm_endpoint: str
    local_llm_model: str
    log_level: str
    log_file_path: str
    ffmpeg_path: str

    @classmethod
    def from_env(cls) -> "BotConfig":
        raw_app_id = os.getenv("DISCORD_APPLICATION_ID", "").strip()
        raw_guild_id = os.getenv("DISCORD_TEST_GUILD_ID", "").strip()
        raw_owner_id = os.getenv("BOT_OWNER_ID", "987654321098765432").strip()

        return cls(
            discord_token=os.getenv("DISCORD_BOT_TOKEN", "").strip(),
            application_id=int(raw_app_id) if raw_app_id.isdigit() else None,
            test_guild_id=int(raw_guild_id) if raw_guild_id.isdigit() else None,
            database_path=os.getenv("DATABASE_PATH", "data/cosmic_baddie.db").strip() or "data/cosmic_baddie.db",
            bot_owner_id=int(raw_owner_id) if raw_owner_id.isdigit() else 987654321098765432,
            default_prefix=os.getenv("DEFAULT_PREFIX", "!").strip() or "!",
            local_llm_endpoint=os.getenv("LOCAL_LLM_ENDPOINT", "").strip(),
            local_llm_model=os.getenv("LOCAL_LLM_MODEL", "llama3.2:1b").strip() or "llama3.2:1b",
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
            log_file_path=os.getenv("LOG_FILE_PATH", "logs/cosmic_baddie.log").strip() or "logs/cosmic_baddie.log",
            ffmpeg_path=os.getenv("FFMPEG_PATH", "ffmpeg").strip() or "ffmpeg",
        )


def setup_logging(config: BotConfig) -> None:
    """Configure structured console and file logging."""
    log_path = Path(config.log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, config.log_level, logging.INFO)
    fmt = "%(asctime)s | %(levelname)-8s | %(name)-28s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_path, encoding="utf-8"),
    ]
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, handlers=handlers, force=True)
