"""
Auto Responder Cog (`/autoresponder`) for Cosmic ki baddie.

Implements all 7 required `/autoresponder` slash commands:
- `/autoresponder create`
- `/autoresponder edit`
- `/autoresponder delete`
- `/autoresponder list`
- `/autoresponder enable`
- `/autoresponder disable`
- `/autoresponder test`

Features:
- Exact & Partial keyword matching
- Case sensitivity toggle
- Multiple responses (random rotation)
- Cooldowns per trigger
- Channel & Role restrictions
- Embed or plain text responses with optional user mention
"""

from __future__ import annotations

import json
import random
import time
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from bot.core.discord_compat import app_commands, commands, discord
from bot.database.models import PermissionLevel
from bot.utils.checks import require_permission_level

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot


class AutoResponderCog(commands.Cog):
    """Keyword-driven Auto Responder with exact/partial matching, cooldowns, and restrictions."""

    autoresponder_group = app_commands.Group(
        name="autoresponder",
        description="Manage automated keyword and phrase triggers.",
    )

    def __init__(self, bot: "CosmicBot") -> None:
        self.bot = bot
        self._cooldowns: Dict[Tuple[int, int], float] = {}

    def match_trigger(self, content: str, rule: Dict[str, Any]) -> bool:
        """Evaluate whether a message matches an auto-responder rule."""
        if not bool(rule.get("enabled", 1)):
            return False
        case_sensitive = bool(rule.get("case_sensitive", 0))
        haystack = content if case_sensitive else content.lower()
        needle = rule["trigger_phrase"] if case_sensitive else rule["trigger_phrase"].lower()
        mode = rule.get("match_mode", "partial")
        if mode == "exact":
            return haystack.strip() == needle.strip()
        return needle in haystack

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        guild = getattr(message, "guild", None)
        author = getattr(message, "author", None)
        if guild is None or author is None or getattr(author, "bot", False):
            return
        content = getattr(message, "content", "") or ""
        if not content:
            return

        rules = await self.bot.db.fetch_all(
            "SELECT * FROM auto_responders WHERE guild_id = ? AND enabled = 1;",
            (int(guild.id),),
        )
        now = time.monotonic()

        for rule in rules:
            if not self.match_trigger(content, rule):
                continue

            # Check channel restriction
            allowed_chs = json.loads(rule.get("allowed_channels_json") or "[]")
            if allowed_chs and int(message.channel.id) not in allowed_chs:
                continue

            # Check role restriction
            allowed_roles = set(json.loads(rule.get("allowed_roles_json") or "[]"))
            if allowed_roles:
                user_roles = {int(r.id) for r in getattr(author, "roles", [])}
                if not (allowed_roles & user_roles):
                    continue

            # Cooldown check
            cd_key = (int(guild.id), int(rule["trigger_id"]))
            cooldown = int(rule.get("cooldown_seconds") or 10)
            if now - self._cooldowns.get(cd_key, 0.0) < cooldown:
                continue
            self._cooldowns[cd_key] = now

            responses = json.loads(rule.get("responses_json") or "[]")
            if not responses:
                continue
            chosen = random.choice(responses)
            prefix_mention = f"<@{author.id}> " if bool(rule.get("mention_user", 1)) else ""

            if bool(rule.get("use_embed", 0)):
                embed = discord.Embed(description=chosen, color=discord.Color.blurple())
                await message.channel.send(content=prefix_mention.strip() or None, embed=embed)
            else:
                await message.channel.send(content=f"{prefix_mention}{chosen}")
            break

    @autoresponder_group.command(name="create", description="Create a new auto-responder trigger rule.")
    @app_commands.describe(
        trigger="Keyword or phrase that triggers the response",
        response="Response text (separate multiple variations with `|`)",
        match_mode="Match mode: exact or partial",
        case_sensitive="Whether matching is case-sensitive",
        use_embed="Send the response inside an embed",
        mention_user="Mention the triggering user",
        cooldown_seconds="Cooldown in seconds between triggers",
    )
    @require_permission_level(PermissionLevel.MODERATOR, module_name="auto_responder")
    async def ar_create(
        self,
        interaction: discord.Interaction,
        trigger: str,
        response: str,
        match_mode: str = "partial",
        case_sensitive: bool = False,
        use_embed: bool = False,
        mention_user: bool = True,
        cooldown_seconds: int = 10,
    ) -> None:
        if interaction.guild is None:
            return
        clean_mode = match_mode.strip().lower()
        if clean_mode not in ("exact", "partial"):
            clean_mode = "partial"
        responses = [r.strip() for r in response.split("|") if r.strip()]
        await self.bot.db.execute(
            """
            INSERT INTO auto_responders (
                guild_id, trigger_phrase, match_mode, case_sensitive,
                responses_json, use_embed, mention_user, cooldown_seconds, enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(guild_id, trigger_phrase) DO UPDATE SET
                match_mode = excluded.match_mode,
                case_sensitive = excluded.case_sensitive,
                responses_json = excluded.responses_json,
                use_embed = excluded.use_embed,
                mention_user = excluded.mention_user,
                cooldown_seconds = excluded.cooldown_seconds;
            """,
            (
                int(interaction.guild.id),
                trigger.strip(),
                clean_mode,
                1 if case_sensitive else 0,
                json.dumps(responses),
                1 if use_embed else 0,
                1 if mention_user else 0,
                max(0, int(cooldown_seconds)),
            ),
        )
        await interaction.response.send_message(
            f"Created auto-responder trigger `{trigger.strip()}` (`mode={clean_mode}`, {len(responses)} response variation(s)).",
            ephemeral=True,
        )

    @autoresponder_group.command(name="edit", description="Update an existing auto-responder trigger's response or mode.")
    @app_commands.describe(trigger="Existing trigger phrase", response="Updated response(s) separated by `|`", match_mode="exact or partial")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="auto_responder")
    async def ar_edit(
        self,
        interaction: discord.Interaction,
        trigger: str,
        response: str,
        match_mode: str = "partial",
    ) -> None:
        if interaction.guild is None:
            return
        responses = [r.strip() for r in response.split("|") if r.strip()]
        await self.bot.db.execute(
            "UPDATE auto_responders SET responses_json = ?, match_mode = ? WHERE guild_id = ? AND trigger_phrase = ?;",
            (json.dumps(responses), match_mode.strip().lower(), int(interaction.guild.id), trigger.strip()),
        )
        await interaction.response.send_message(f"Updated auto-responder `{trigger.strip()}`.", ephemeral=True)

    @autoresponder_group.command(name="delete", description="Delete an auto-responder trigger.")
    @app_commands.describe(trigger="Trigger phrase to delete")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="auto_responder")
    async def ar_delete(self, interaction: discord.Interaction, trigger: str) -> None:
        if interaction.guild is None:
            return
        await self.bot.db.execute(
            "DELETE FROM auto_responders WHERE guild_id = ? AND trigger_phrase = ?;",
            (int(interaction.guild.id), trigger.strip()),
        )
        await interaction.response.send_message(f"Deleted auto-responder `{trigger.strip()}`.", ephemeral=True)

    @autoresponder_group.command(name="list", description="List all configured auto-responder triggers in this server.")
    async def ar_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        rows = await self.bot.db.fetch_all(
            "SELECT * FROM auto_responders WHERE guild_id = ? ORDER BY trigger_id ASC;",
            (int(interaction.guild.id),),
        )
        embed = discord.Embed(title=f"Auto-Responder Triggers ({len(rows)})", color=discord.Color.blurple())
        if not rows:
            embed.description = "No auto-responders configured. Use `/autoresponder create`."
        else:
            embed.description = "\n".join(
                f"• `{r['trigger_phrase']}` (`{r['match_mode']}`) · {'Enabled' if r['enabled'] else 'Disabled'} · Cooldown: `{r['cooldown_seconds']}s`"
                for r in rows
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @autoresponder_group.command(name="enable", description="Enable a specific auto-responder trigger.")
    @app_commands.describe(trigger="Trigger phrase to enable")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="auto_responder")
    async def ar_enable(self, interaction: discord.Interaction, trigger: str) -> None:
        if interaction.guild is None:
            return
        await self.bot.db.execute(
            "UPDATE auto_responders SET enabled = 1 WHERE guild_id = ? AND trigger_phrase = ?;",
            (int(interaction.guild.id), trigger.strip()),
        )
        await interaction.response.send_message(f"Enabled auto-responder `{trigger.strip()}`.", ephemeral=True)

    @autoresponder_group.command(name="disable", description="Disable a specific auto-responder trigger.")
    @app_commands.describe(trigger="Trigger phrase to disable")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="auto_responder")
    async def ar_disable(self, interaction: discord.Interaction, trigger: str) -> None:
        if interaction.guild is None:
            return
        await self.bot.db.execute(
            "UPDATE auto_responders SET enabled = 0 WHERE guild_id = ? AND trigger_phrase = ?;",
            (int(interaction.guild.id), trigger.strip()),
        )
        await interaction.response.send_message(f"Disabled auto-responder `{trigger.strip()}`.", ephemeral=True)

    @autoresponder_group.command(name="test", description="Test a sample message against all active auto-responder triggers.")
    @app_commands.describe(sample_message="Sample text message to test matching against")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="auto_responder")
    async def ar_test(self, interaction: discord.Interaction, sample_message: str) -> None:
        if interaction.guild is None:
            return
        rules = await self.bot.db.fetch_all(
            "SELECT * FROM auto_responders WHERE guild_id = ? AND enabled = 1;",
            (int(interaction.guild.id),),
        )
        for rule in rules:
            if self.match_trigger(sample_message, rule):
                responses = json.loads(rule.get("responses_json") or "[]")
                preview = responses[0] if responses else "(Empty)"
                await interaction.response.send_message(
                    f"Matched trigger `{rule['trigger_phrase']}` (`{rule['match_mode']}`) → Response: {preview}",
                    ephemeral=True,
                )
                return
        await interaction.response.send_message("No active auto-responder trigger matched that sample message.", ephemeral=True)


async def setup(bot: "CosmicBot") -> None:
    await bot.add_cog(AutoResponderCog(bot))
