"""
Personal AI Assistant Cog (`/ai`) for Cosmic ki baddie.

Implements all 10 required `/ai` slash commands (including `knowledge` subgroup):
- `/ai setup`
- `/ai enable`
- `/ai disable`
- `/ai personality`
- `/ai knowledge add`
- `/ai knowledge edit`
- `/ai knowledge remove`
- `/ai knowledge list`
- `/ai reset`
- `/ai status`
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional

from bot.core.discord_compat import app_commands, commands, discord
from bot.database.models import PermissionLevel
from bot.ui.dashboard import SetupDashboardView
from bot.utils.checks import require_permission_level

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot


class AIAssistantCog(commands.Cog):
    """Zero-API-key Local Assistant with Knowledge Base, Intent Classification, and Optional Local LLM."""

    ai_group = app_commands.Group(
        name="ai",
        description="Configure and interact with Cosmic ki baddie's zero-API-key Local AI Assistant.",
    )
    knowledge_group = app_commands.Group(
        name="knowledge",
        description="Manage custom server knowledge base entries for the AI Assistant.",
        parent=ai_group,
    )

    def __init__(self, bot: "CosmicBot") -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Respond when users mention the bot or prefix a question with `@Cosmic ki baddie`."""
        guild = getattr(message, "guild", None)
        author = getattr(message, "author", None)
        if guild is None or author is None or getattr(author, "bot", False):
            return
        content = getattr(message, "content", "") or ""
        bot_id = getattr(getattr(self.bot, "user", None), "id", None)
        if not bot_id or (f"<@{bot_id}>" not in content and f"<@!{bot_id}>" not in content):
            return

        cleaned_prompt = content.replace(f"<@{bot_id}>", "").replace(f"<@!{bot_id}>", "").strip()
        if not cleaned_prompt:
            cleaned_prompt = "hello"

        role_ids = [int(r.id) for r in getattr(author, "roles", [])]
        ok, reply_text, _ = await self.bot.ai_service.generate_response(
            guild_id=int(guild.id),
            user_id=int(author.id),
            username=getattr(author, "display_name", getattr(author, "name", "User")),
            prompt=cleaned_prompt,
            channel_id=int(message.channel.id),
            member_role_ids=role_ids,
        )
        if ok:
            await message.reply(reply_text)

    @ai_group.command(name="setup", description="Open the interactive AI Assistant Configuration Panel.")
    @require_permission_level(PermissionLevel.ADMIN, module_name="ai_assistant")
    async def ai_setup(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await self.bot.ai_service.ensure_config(int(interaction.guild.id))
        view = SetupDashboardView(self.bot, author_id=int(interaction.user.id), initial_page="ai_assistant")
        embed = await view.build_page_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @ai_group.command(name="enable", description="Enable the Local AI Assistant in this server.")
    @require_permission_level(PermissionLevel.ADMIN, module_name="ai_assistant")
    async def ai_enable(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await self.bot.ai_service.update_config(int(interaction.guild.id), enabled=1)
        await interaction.response.send_message("Enabled the Local AI Assistant for this server.", ephemeral=True)

    @ai_group.command(name="disable", description="Disable the Local AI Assistant in this server.")
    @require_permission_level(PermissionLevel.ADMIN, module_name="ai_assistant")
    async def ai_disable(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await self.bot.ai_service.update_config(int(interaction.guild.id), enabled=0)
        await interaction.response.send_message("Disabled the Local AI Assistant for this server.", ephemeral=True)

    @ai_group.command(name="personality", description="Configure the AI Assistant's personality, response style, and greeting.")
    @app_commands.describe(
        personality="System persona description",
        response_style="Style: concise, balanced, or detailed",
        greeting_template="Greeting template using {user} placeholder",
        cooldown_seconds="Per-user query cooldown in seconds",
    )
    @require_permission_level(PermissionLevel.ADMIN, module_name="ai_assistant")
    async def ai_personality(
        self,
        interaction: discord.Interaction,
        personality: str,
        response_style: str = "balanced",
        greeting_template: Optional[str] = None,
        cooldown_seconds: int = 5,
    ) -> None:
        if interaction.guild is None:
            return
        clean_style = response_style.strip().lower()
        if clean_style not in ("concise", "balanced", "detailed"):
            clean_style = "balanced"
        updates = {
            "personality": personality.strip(),
            "response_style": clean_style,
            "cooldown_seconds": max(1, min(120, int(cooldown_seconds))),
        }
        if greeting_template:
            updates["greeting_template"] = greeting_template.strip()
        cfg = await self.bot.ai_service.update_config(int(interaction.guild.id), **updates)
        await interaction.response.send_message(
            f"Updated AI Assistant personality (`style={cfg['response_style']}`, `cooldown={cfg['cooldown_seconds']}s`).",
            ephemeral=True,
        )

    @knowledge_group.command(name="add", description="Add a topic and response to the server's local AI knowledge base.")
    @app_commands.describe(
        topic="Unique topic identifier (e.g. server_ip,appeals,vip_perks)",
        keywords="Comma-separated trigger keywords",
        response="Answer text returned when matched",
        intent="Intent category (faq, support, moderation, voice, music)",
    )
    @require_permission_level(PermissionLevel.ADMIN, module_name="ai_assistant")
    async def ai_knowledge_add(
        self,
        interaction: discord.Interaction,
        topic: str,
        keywords: str,
        response: str,
        intent: str = "faq",
    ) -> None:
        if interaction.guild is None:
            return
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
        await self.bot.ai_service.add_knowledge(
            guild_id=int(interaction.guild.id),
            topic=topic,
            keywords=kw_list,
            response_text=response,
            intent_category=intent,
        )
        await interaction.response.send_message(
            f"Added knowledge topic `{topic.strip().lower()}` with {len(kw_list)} keyword(s).",
            ephemeral=True,
        )

    @knowledge_group.command(name="edit", description="Update an existing topic in the server's local AI knowledge base.")
    @app_commands.describe(topic="Existing topic identifier", keywords="Updated comma-separated keywords", response="Updated answer text")
    @require_permission_level(PermissionLevel.ADMIN, module_name="ai_assistant")
    async def ai_knowledge_edit(
        self,
        interaction: discord.Interaction,
        topic: str,
        keywords: str,
        response: str,
    ) -> None:
        if interaction.guild is None:
            return
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
        await self.bot.ai_service.add_knowledge(
            guild_id=int(interaction.guild.id),
            topic=topic,
            keywords=kw_list,
            response_text=response,
        )
        await interaction.response.send_message(f"Updated knowledge topic `{topic.strip().lower()}`.", ephemeral=True)

    @knowledge_group.command(name="remove", description="Remove a topic from the server's local AI knowledge base.")
    @app_commands.describe(topic="Topic identifier to remove")
    @require_permission_level(PermissionLevel.ADMIN, module_name="ai_assistant")
    async def ai_knowledge_remove(self, interaction: discord.Interaction, topic: str) -> None:
        if interaction.guild is None:
            return
        removed = await self.bot.ai_service.remove_knowledge(int(interaction.guild.id), topic)
        if not removed:
            await interaction.response.send_message(f"Knowledge topic `{topic}` not found.", ephemeral=True)
            return
        await interaction.response.send_message(f"Removed knowledge topic `{topic}`.", ephemeral=True)

    @knowledge_group.command(name="list", description="List all topics stored in the server's local AI knowledge base.")
    async def ai_knowledge_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        entries = await self.bot.ai_service.list_knowledge(int(interaction.guild.id))
        embed = discord.Embed(
            title=f"Local AI Knowledge Base ({len(entries)} Topics)",
            color=discord.Color.blurple(),
        )
        for e in entries[:15]:
            kws = ", ".join(json.loads(e.get("keywords_json") or "[]"))
            embed.add_field(
                name=f"Topic: {e['topic']} ({e['intent_category']})",
                value=f"Keywords: `{kws}`\nResponse: {e['response_text'][:200]}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ai_group.command(name="reset", description="Clear conversation history memory for this server.")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="ai_assistant")
    async def ai_reset(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        cleared = self.bot.ai_service.reset_conversation_history(int(interaction.guild.id))
        await interaction.response.send_message(
            f"Reset AI conversation history for **{cleared}** active user session(s).",
            ephemeral=True,
        )

    @ai_group.command(name="status", description="View AI Assistant mode, knowledge count, and ask a test question.")
    @app_commands.describe(question="Optional question to ask the local AI Assistant")
    async def ai_status(self, interaction: discord.Interaction, question: Optional[str] = None) -> None:
        if interaction.guild is None:
            return
        cfg = await self.bot.ai_service.ensure_config(int(interaction.guild.id))
        entries = await self.bot.ai_service.list_knowledge(int(interaction.guild.id))

        embed = discord.Embed(
            title="Cosmic ki baddie — Local AI Assistant Status",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Status", value="Enabled" if cfg.get("enabled", 1) else "Disabled", inline=True)
        embed.add_field(name="Active Engine", value=f"`{cfg.get('mode', 'local_kb')}` (Zero External API Key)", inline=True)
        embed.add_field(name="Knowledge Topics", value=str(len(entries)), inline=True)
        embed.add_field(name="Personality", value=cfg.get("personality", "Default"), inline=False)

        if question and question.strip():
            ok, answer, meta = await self.bot.ai_service.generate_response(
                guild_id=int(interaction.guild.id),
                user_id=int(interaction.user.id),
                username=interaction.user.name,
                prompt=question,
                bypass_cooldown=True,
            )
            embed.add_field(
                name=f"Query Response (Intent: {meta.get('intent')})",
                value=answer[:1024],
                inline=False,
            )

        await interaction.response.send_message(embed=embed)


async def setup(bot: "CosmicBot") -> None:
    await bot.add_cog(AIAssistantCog(bot))
