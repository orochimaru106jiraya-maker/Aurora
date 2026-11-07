"""
Custom Embed Builder Cog (`/embed`) for Cosmic ki baddie.

Implements all 7 required `/embed` slash commands:
- `/embed create`
- `/embed edit`
- `/embed preview`
- `/embed publish`
- `/embed save`
- `/embed list`
- `/embed delete`
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING, Any, Dict, Optional

from bot.core.discord_compat import app_commands, commands, discord
from bot.database.models import PermissionLevel
from bot.utils.checks import require_permission_level
from bot.utils.validators import is_valid_http_url, validate_hex_color

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot


def build_discord_embed_from_record(rec: Dict[str, Any]) -> discord.Embed:
    """Construct a discord.Embed from a saved `embed_templates` SQLite row."""
    _, color_int = validate_hex_color(rec.get("color_hex") or "#6366F1")
    ts = datetime.now(timezone.utc) if bool(rec.get("include_timestamp", 1)) else None
    embed = discord.Embed(
        title=rec.get("title") or "Untitled Embed",
        description=rec.get("description") or "",
        color=discord.Color(color_int),
        timestamp=ts,
    )
    if rec.get("author_name"):
        icon = rec.get("author_icon_url") if is_valid_http_url(rec.get("author_icon_url", "")) else None
        embed.set_author(name=rec["author_name"], icon_url=icon)
    if rec.get("footer_text"):
        embed.set_footer(text=rec["footer_text"])
    if is_valid_http_url(rec.get("thumbnail_url", "")):
        embed.set_thumbnail(url=rec["thumbnail_url"])
    if is_valid_http_url(rec.get("image_url", "")):
        embed.set_image(url=rec["image_url"])

    fields = json.loads(rec.get("fields_json") or "[]")
    for f in fields[:25]:
        embed.add_field(
            name=str(f.get("name", "Field")),
            value=str(f.get("value", "...")),
            inline=bool(f.get("inline", True)),
        )
    return embed


class EmbedBuilderCog(commands.Cog):
    """Interactive Discord Embed Builder and SQLite Template Library."""

    embed_group = app_commands.Group(
        name="embed",
        description="Create, edit, preview, save, and publish reusable custom Discord embeds.",
    )

    def __init__(self, bot: "CosmicBot") -> None:
        self.bot = bot

    @embed_group.command(name="create", description="Create a new custom embed template and store it in SQLite.")
    @app_commands.describe(
        template_name="Unique template identifier",
        title="Embed title",
        description="Embed description body",
        color_hex="Hex color code (e.g. #6366F1)",
        footer_text="Optional footer text",
        author_name="Optional author header text",
        thumbnail_url="Optional thumbnail HTTP/HTTPS image URL",
        image_url="Optional main banner HTTP/HTTPS image URL",
    )
    @require_permission_level(PermissionLevel.MODERATOR, module_name="embeds")
    async def embed_create(
        self,
        interaction: discord.Interaction,
        template_name: str,
        title: str,
        description: str,
        color_hex: str = "#6366F1",
        footer_text: str = "",
        author_name: str = "",
        thumbnail_url: str = "",
        image_url: str = "",
    ) -> None:
        if interaction.guild is None:
            return
        valid_color, _ = validate_hex_color(color_hex)
        if not valid_color:
            await interaction.response.send_message("Invalid hex color. Use format `#6366F1`.", ephemeral=True)
            return

        clean_name = template_name.strip().lower()
        await self.bot.db.execute(
            """
            INSERT INTO embed_templates (
                guild_id, template_name, title, description, color_hex,
                author_name, footer_text, thumbnail_url, image_url, created_by_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(guild_id, template_name) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                color_hex = excluded.color_hex,
                author_name = excluded.author_name,
                footer_text = excluded.footer_text,
                thumbnail_url = excluded.thumbnail_url,
                image_url = excluded.image_url,
                updated_at = datetime('now');
            """,
            (
                int(interaction.guild.id),
                clean_name,
                title,
                description,
                color_hex.strip(),
                author_name,
                footer_text,
                thumbnail_url,
                image_url,
                int(interaction.user.id),
            ),
        )
        row = await self.bot.db.fetch_one(
            "SELECT * FROM embed_templates WHERE guild_id = ? AND template_name = ?;",
            (int(interaction.guild.id), clean_name),
        )
        preview = build_discord_embed_from_record(row or {"title": title, "description": description, "color_hex": color_hex})
        await interaction.response.send_message(
            content=f"Created embed template `{clean_name}`:",
            embed=preview,
            ephemeral=True,
        )

    @embed_group.command(name="edit", description="Edit an existing embed template or append a custom field to it.")
    @app_commands.describe(
        template_name="Template identifier to edit",
        title="New title (optional)",
        description="New description (optional)",
        field_name="Optional field name to append",
        field_value="Optional field value to append",
    )
    @require_permission_level(PermissionLevel.MODERATOR, module_name="embeds")
    async def embed_edit(
        self,
        interaction: discord.Interaction,
        template_name: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        field_name: Optional[str] = None,
        field_value: Optional[str] = None,
    ) -> None:
        if interaction.guild is None:
            return
        clean_name = template_name.strip().lower()
        row = await self.bot.db.fetch_one(
            "SELECT * FROM embed_templates WHERE guild_id = ? AND template_name = ?;",
            (int(interaction.guild.id), clean_name),
        )
        if not row:
            await interaction.response.send_message(f"Embed template `{clean_name}` not found.", ephemeral=True)
            return

        new_title = title if title is not None else row["title"]
        new_desc = description if description is not None else row["description"]
        fields = json.loads(row.get("fields_json") or "[]")
        if field_name and field_value:
            fields.append({"name": field_name, "value": field_value, "inline": True})

        await self.bot.db.execute(
            """
            UPDATE embed_templates
            SET title = ?, description = ?, fields_json = ?, updated_at = datetime('now')
            WHERE guild_id = ? AND template_name = ?;
            """,
            (new_title, new_desc, json.dumps(fields), int(interaction.guild.id), clean_name),
        )
        await interaction.response.send_message(f"Updated embed template `{clean_name}`.", ephemeral=True)

    @embed_group.command(name="preview", description="Preview a saved embed template ephemerally.")
    @app_commands.describe(template_name="Template identifier to preview")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="embeds")
    async def embed_preview(self, interaction: discord.Interaction, template_name: str) -> None:
        if interaction.guild is None:
            return
        row = await self.bot.db.fetch_one(
            "SELECT * FROM embed_templates WHERE guild_id = ? AND template_name = ?;",
            (int(interaction.guild.id), template_name.strip().lower()),
        )
        if not row:
            await interaction.response.send_message(f"Template `{template_name}` not found.", ephemeral=True)
            return
        embed = build_discord_embed_from_record(row)
        await interaction.response.send_message(content=f"Preview of `{template_name}`:", embed=embed, ephemeral=True)

    @embed_group.command(name="publish", description="Publish a saved embed template to a target channel.")
    @app_commands.describe(template_name="Template identifier to publish", channel="Destination channel (defaults to current)")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="embeds")
    async def embed_publish(
        self,
        interaction: discord.Interaction,
        template_name: str,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if interaction.guild is None:
            return
        row = await self.bot.db.fetch_one(
            "SELECT * FROM embed_templates WHERE guild_id = ? AND template_name = ?;",
            (int(interaction.guild.id), template_name.strip().lower()),
        )
        if not row:
            await interaction.response.send_message(f"Template `{template_name}` not found.", ephemeral=True)
            return
        target_ch = channel or interaction.channel
        embed = build_discord_embed_from_record(row)
        await target_ch.send(embed=embed)
        await interaction.response.send_message(
            f"Published embed template `{template_name}` to {target_ch.mention}.",
            ephemeral=True,
        )

    @embed_group.command(name="save", description="Duplicate or save an embed template under a new name.")
    @app_commands.describe(source_name="Existing template name", new_name="New template name to save as")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="embeds")
    async def embed_save(self, interaction: discord.Interaction, source_name: str, new_name: str) -> None:
        if interaction.guild is None:
            return
        row = await self.bot.db.fetch_one(
            "SELECT * FROM embed_templates WHERE guild_id = ? AND template_name = ?;",
            (int(interaction.guild.id), source_name.strip().lower()),
        )
        if not row:
            await interaction.response.send_message(f"Source template `{source_name}` not found.", ephemeral=True)
            return
        await self.bot.db.execute(
            """
            INSERT INTO embed_templates (
                guild_id, template_name, title, description, color_hex,
                author_name, footer_text, thumbnail_url, image_url, fields_json, created_by_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, template_name) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                fields_json = excluded.fields_json;
            """,
            (
                int(interaction.guild.id),
                new_name.strip().lower(),
                row["title"],
                row["description"],
                row["color_hex"],
                row["author_name"],
                row["footer_text"],
                row["thumbnail_url"],
                row["image_url"],
                row["fields_json"],
                int(interaction.user.id),
            ),
        )
        await interaction.response.send_message(f"Saved template copy as `{new_name.strip().lower()}`.", ephemeral=True)

    @embed_group.command(name="list", description="List all saved embed templates in this server.")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="embeds")
    async def embed_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        rows = await self.bot.db.fetch_all(
            "SELECT * FROM embed_templates WHERE guild_id = ? ORDER BY template_name ASC;",
            (int(interaction.guild.id),),
        )
        embed = discord.Embed(title=f"Saved Embed Templates ({len(rows)})", color=discord.Color.blurple())
        if not rows:
            embed.description = "No embed templates saved yet. Use `/embed create`."
        else:
            embed.description = "\n".join(
                f"• `{r['template_name']}` — **{r['title']}** (`{r['color_hex']}`)" for r in rows
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @embed_group.command(name="delete", description="Delete a saved embed template.")
    @app_commands.describe(template_name="Template identifier to delete")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="embeds")
    async def embed_delete(self, interaction: discord.Interaction, template_name: str) -> None:
        if interaction.guild is None:
            return
        await self.bot.db.execute(
            "DELETE FROM embed_templates WHERE guild_id = ? AND template_name = ?;",
            (int(interaction.guild.id), template_name.strip().lower()),
        )
        await interaction.response.send_message(f"Deleted embed template `{template_name.strip().lower()}`.", ephemeral=True)


async def setup(bot: "CosmicBot") -> None:
    await bot.add_cog(EmbedBuilderCog(bot))
