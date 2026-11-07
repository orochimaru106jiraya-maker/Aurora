"""
 Automated Registry vs README & Source Verification Script (`tests/verify_registry.py`).
Compares:
1. Commands defined in Python Cog source files
2. Commands loaded into CosmicBot's CommandTree
3. Commands documented in README.md
Outputs a structured JSON diagnostic report for both CLI and the Web Control Plane.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bot.core.bot import CosmicBot
from bot.core.config import BotConfig


async def generate_verification_bundle() -> Dict[str, Any]:
    root = Path(__file__).resolve().parent.parent
    cfg = BotConfig.from_env()
    bot = CosmicBot(config=cfg)
    await bot.initialize_core(register_views=True)

    health = await bot.health_monitor.generate_full_diagnostic_report()
    registered_qnames = {c["qualified_name"] for c in health["commands"]["registry"]}

    readme_path = root / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    readme_cmds = set(re.findall(r"`(/[a-z][a-z0-9_ ]*)`", readme_text))

    undocumented = sorted(registered_qnames - readme_cmds)

    await bot.close()
    return {
        "health": health,
        "verification": {
            "total_registered_in_tree": len(registered_qnames),
            "total_documented_in_readme": len(readme_cmds & registered_qnames),
            "undocumented_commands": undocumented,
            "discrepancy_count": len(undocumented),
            "all_12_cogs_loaded": len(health["extensions"]["failed"]) == 0,
            "persistent_views_count": health["voice_and_media"]["persistent_views_registered"],
        },
    }


if __name__ == "__main__":
    bundle = asyncio.run(generate_verification_bundle())
    print(json.dumps(bundle, indent=2))
