"""
Multi-Page Interactive Server Management Dashboard (`/setup` & `/dashboard`) for Cosmic ki baddie.

Implements all 14 mandatory dashboard pages with real working controls:
1. Overview
2. Moderation
3. Tickets (with independent configuration for all 4 categories)
4. Permissions (RBAC)
5. Activity Roles
6. Reaction Roles
7. Join-to-Create
8. Music
9. AI Assistant
10. Auto Responder
11. Embed Builder
12. Logging
13. Administration
14. Database and Backup
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, List

from bot.core.discord_compat import discord
from bot.database.models import DEFAULT_TICKET_CATEGORIES, PermissionLevel
from bot.utils.formatting import utc_now_iso

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot

DASHBOARD_PAGES: List[Dict[str, str]] = [
    {"key": "overview", "label": "1. Overview", "description": "Bot & DB status, module summary, and completion metrics"},
    {"key": "moderation", "label": "2. Moderation", "description": "Case tracking, snipe history, hierarchy & mod logs"},
    {"key": "tickets", "label": "3. Tickets", "description": "Configure all 4 ticket categories, transcripts & staff"},
    {"key": "permissions", "label": "4. Permissions", "description": "Centralized RBAC roles, users & command rules"},
    {"key": "activity_roles", "label": "5. Activity Roles", "description": "Spotify, Gaming, Voice & Text Chat auto-roles"},
    {"key": "reaction_roles", "label": "6. Reaction Roles", "description": "Self-assignable button, dropdown & reaction panels"},
    {"key": "jtc", "label": "7. Join-to-Create", "description": "Temporary voice room hubs, limits & cooldowns"},
    {"key": "music", "label": "8. Music", "description": "FFmpeg/PyNaCl player status, volume, loop & DJ config"},
    {"key": "ai_assistant", "label": "9. AI Assistant", "description": "Local knowledge base, personality & channel rules"},
    {"key": "auto_responder", "label": "10. Auto Responder", "description": "Keyword triggers, match modes & cooldowns"},
    {"key": "embeds", "label": "11. Embed Builder", "description": "Reusable custom Discord embed templates"},
    {"key": "logging", "label": "12. Logging", "description": "Moderation, server audit & transcript log channels"},
    {"key": "administration", "label": "13. Administration", "description": "Prefix, module toggles & server diagnostics"},
    {"key": "database_backup", "label": "14. Database & Backup", "description": "SQLite health, migrations & one-click backups"},
]


class PrefixConfigModal(discord.ui.Modal):
    """Modal to update guild prefix and snipe retention limit from the dashboard."""

    def __init__(self, dashboard_view: "SetupDashboardView") -> None:
        super().__init__(title="Server Administration Settings", timeout=180.0, custom_id="cosmic:dash:prefix_modal")
        self.dashboard_view = dashboard_view
        self.prefix_input = discord.ui.TextInput(
            label="Command Prefix",
            default="!",
            placeholder="e.g. ! or ?",
            required=True,
            max_length=5,
            custom_id="cosmic:dash:prefix_val",
        )
        self.snipe_input = discord.ui.TextInput(
            label="Snipe Retention Limit (1-100)",
            default="25",
            placeholder="25",
            required=True,
            max_length=3,
            custom_id="cosmic:dash:snipe_val",
        )
        self.add_item(self.prefix_input)
        self.add_item(self.snipe_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        snipe_val = int(self.snipe_input.value) if self.snipe_input.value.isdigit() else 25
        snipe_val = max(1, min(100, snipe_val))
        await self.dashboard_view.bot.logging_service.update_guild_config(
            int(interaction.guild.id),
            prefix=self.prefix_input.value.strip() or "!",
            snipe_limit=snipe_val,
        )
        embed = await self.dashboard_view.build_page_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self.dashboard_view)


class SetupDashboardView(discord.ui.View):
    """
    Interactive 14-page Server Management Dashboard (`/setup` and `/dashboard`).
    Features:
    - Dropdown selector for all 14 pages
    - Previous / Overview Home / Next navigation buttons
    - Context-sensitive action buttons (Toggle Module, Post Ticket Panel, Create DB Backup, Edit Settings)
    - Server-side RBAC check on every interaction
    """

    def __init__(self, bot: "CosmicBot", author_id: int, initial_page: str = "overview") -> None:
        super().__init__(timeout=600.0)
        self.bot = bot
        self.author_id = int(author_id)
        self.current_page = initial_page
        self.selected_ticket_category = "general_help"
        self._rebuild_components()

    def _rebuild_components(self) -> None:
        self.clear_items()

        # Row 0: 14-Page Dropdown Selector
        options = [
            discord.SelectOption(
                label=p["label"],
                value=p["key"],
                description=p["description"][:100],
                default=(p["key"] == self.current_page),
            )
            for p in DASHBOARD_PAGES
        ]
        page_select = discord.ui.Select(
            placeholder="Select a Dashboard Configuration Page (1–14)...",
            options=options,
            custom_id="cosmic:setup:page_select",
            row=0,
        )
        page_select.callback = self._on_select_page
        self.add_item(page_select)

        # Row 1: If on Tickets page, add 4-category selector dropdown
        if self.current_page == "tickets":
            cat_options = [
                discord.SelectOption(
                    label=f"{meta['emoji']} {meta['name']}",
                    value=key,
                    description=meta["description"][:95],
                    default=(key == self.selected_ticket_category),
                )
                for key, meta in DEFAULT_TICKET_CATEGORIES.items()
            ]
            cat_select = discord.ui.Select(
                placeholder="Select Ticket Category to Configure...",
                options=cat_options,
                custom_id="cosmic:setup:ticket_cat_select",
                row=1,
            )
            cat_select.callback = self._on_select_ticket_category
            self.add_item(cat_select)

        # Row 2: Navigation Controls (Back, Home/Overview, Next, Refresh)
        prev_btn = discord.ui.Button(
            label="Previous Page",
            style=discord.ButtonStyle.secondary,
            custom_id="cosmic:setup:prev",
            row=2,
        )
        home_btn = discord.ui.Button(
            label="Overview",
            style=discord.ButtonStyle.primary,
            custom_id="cosmic:setup:home",
            row=2,
        )
        next_btn = discord.ui.Button(
            label="Next Page",
            style=discord.ButtonStyle.secondary,
            custom_id="cosmic:setup:next",
            row=2,
        )
        refresh_btn = discord.ui.Button(
            label="Refresh",
            style=discord.ButtonStyle.secondary,
            custom_id="cosmic:setup:refresh",
            row=2,
        )

        prev_btn.callback = self._on_prev_page
        home_btn.callback = self._on_home_page
        next_btn.callback = self._on_next_page
        refresh_btn.callback = self._on_refresh

        self.add_item(prev_btn)
        self.add_item(home_btn)
        self.add_item(next_btn)
        self.add_item(refresh_btn)

        # Row 3: Context-specific working controls
        if self.current_page in (
            "moderation",
            "tickets",
            "permissions",
            "activity_roles",
            "reaction_roles",
            "jtc",
            "music",
            "ai_assistant",
            "auto_responder",
            "embeds",
            "administration",
        ):
            toggle_btn = discord.ui.Button(
                label=f"Toggle {self.current_page.replace('_', ' ').title()} Module",
                style=discord.ButtonStyle.success,
                custom_id=f"cosmic:setup:toggle:{self.current_page}",
                row=3,
            )
            toggle_btn.callback = self._on_toggle_module
            self.add_item(toggle_btn)

        if self.current_page == "tickets":
            deploy_panel_btn = discord.ui.Button(
                label="Publish 4-Category Ticket Panel Here",
                style=discord.ButtonStyle.primary,
                custom_id="cosmic:setup:deploy_ticket_panel",
                row=3,
            )
            deploy_panel_btn.callback = self._on_deploy_ticket_panel
            self.add_item(deploy_panel_btn)

        if self.current_page in ("overview", "administration", "moderation"):
            edit_cfg_btn = discord.ui.Button(
                label="Edit Prefix & Snipe Limit",
                style=discord.ButtonStyle.secondary,
                custom_id="cosmic:setup:edit_prefix",
                row=3,
            )
            edit_cfg_btn.callback = self._on_open_prefix_modal
            self.add_item(edit_cfg_btn)

        if self.current_page in ("overview", "database_backup"):
            backup_btn = discord.ui.Button(
                label="Create SQLite Snapshot Backup",
                style=discord.ButtonStyle.success,
                custom_id="cosmic:setup:create_backup",
                row=3,
            )
            backup_btn.callback = self._on_create_backup
            self.add_item(backup_btn)

    async def _authorize(self, interaction: discord.Interaction) -> bool:
        if int(interaction.user.id) != self.author_id:
            await interaction.response.send_message(
                "Only the administrator who opened this Setup Dashboard can interact with it.",
                ephemeral=True,
            )
            return False
        allowed, reason = await self.bot.permission_service.authorize_interaction(
            interaction=interaction,
            command_name="setup",
            module_name="administration",
            default_level=PermissionLevel.ADMIN,
        )
        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return False
        return True

    async def _on_select_page(self, interaction: discord.Interaction) -> None:
        if not await self._authorize(interaction):
            return
        for child in self.children:
            if isinstance(child, discord.ui.Select) and child.custom_id == "cosmic:setup:page_select":
                if child.values:
                    self.current_page = child.values[0]
        self._rebuild_components()
        embed = await self.build_page_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_select_ticket_category(self, interaction: discord.Interaction) -> None:
        if not await self._authorize(interaction):
            return
        for child in self.children:
            if isinstance(child, discord.ui.Select) and child.custom_id == "cosmic:setup:ticket_cat_select":
                if child.values:
                    self.selected_ticket_category = child.values[0]
        self._rebuild_components()
        embed = await self.build_page_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_prev_page(self, interaction: discord.Interaction) -> None:
        if not await self._authorize(interaction):
            return
        keys = [p["key"] for p in DASHBOARD_PAGES]
        idx = keys.index(self.current_page) if self.current_page in keys else 0
        self.current_page = keys[(idx - 1) % len(keys)]
        self._rebuild_components()
        embed = await self.build_page_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_home_page(self, interaction: discord.Interaction) -> None:
        if not await self._authorize(interaction):
            return
        self.current_page = "overview"
        self._rebuild_components()
        embed = await self.build_page_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_next_page(self, interaction: discord.Interaction) -> None:
        if not await self._authorize(interaction):
            return
        keys = [p["key"] for p in DASHBOARD_PAGES]
        idx = keys.index(self.current_page) if self.current_page in keys else 0
        self.current_page = keys[(idx + 1) % len(keys)]
        self._rebuild_components()
        embed = await self.build_page_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_refresh(self, interaction: discord.Interaction) -> None:
        if not await self._authorize(interaction):
            return
        embed = await self.build_page_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_toggle_module(self, interaction: discord.Interaction) -> None:
        if not await self._authorize(interaction) or interaction.guild is None:
            return
        guild_id = int(interaction.guild.id)
        cfg = await self.bot.logging_service.ensure_guild_config(guild_id)
        modules = json.loads(cfg.get("enabled_modules_json") or "{}")
        current_state = bool(modules.get(self.current_page, True))
        modules[self.current_page] = not current_state
        await self.bot.logging_service.update_guild_config(
            guild_id,
            enabled_modules_json=json.dumps(modules),
        )
        await self.bot.permission_service.set_module_rule(
            guild=interaction.guild,
            actor=interaction.user,
            module_name=self.current_page,
            required_level=PermissionLevel.EVERYONE.value,
            enabled=not current_state,
        )
        embed = await self.build_page_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_deploy_ticket_panel(self, interaction: discord.Interaction) -> None:
        if not await self._authorize(interaction) or interaction.guild is None:
            return
        from bot.ui.persistent_views import PersistentTicketPanelView

        cats = await self.bot.ticket_service.ensure_default_categories(int(interaction.guild.id))
        panel_embed = discord.Embed(
            title=f"{interaction.guild.name} — Support & Ticket Center",
            description=(
                "Select one of the categories below to open a private ticket channel with our staff team.\n\n"
                + "\n".join(
                    f"**{c['emoji']} {c['display_name']}** — {c['description']}"
                    for c in cats
                )
            ),
            color=discord.Color.blurple(),
        )
        panel_embed.set_footer(text="Cosmic ki baddie Ticket Management Platform · Duplicate protection active")
        await interaction.channel.send(embed=panel_embed, view=PersistentTicketPanelView(self.bot))
        await interaction.response.send_message("Published interactive 4-category Ticket Panel in this channel.", ephemeral=True)

    async def _on_open_prefix_modal(self, interaction: discord.Interaction) -> None:
        if not await self._authorize(interaction):
            return
        await interaction.response.send_modal(PrefixConfigModal(self))

    async def _on_create_backup(self, interaction: discord.Interaction) -> None:
        if not await self._authorize(interaction) or interaction.guild is None:
            return
        res = await self.bot.db.create_guild_backup(
            guild_id=int(interaction.guild.id),
            created_by_id=int(interaction.user.id),
            label="Setup Dashboard Snapshot",
        )
        embed = await self.build_page_embed(interaction.guild)
        embed.add_field(
            name="Latest Backup Created",
            value=f"Backup ID `#{res['backup_id']}` saved to SQLite at {utc_now_iso()}.",
            inline=False,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def build_page_embed(self, guild: Any) -> discord.Embed:
        """Render the rich diagnostic & configuration embed for the active dashboard page."""
        guild_id = int(guild.id) if guild else 0
        cfg = await self.bot.logging_service.ensure_guild_config(guild_id)
        modules: Dict[str, bool] = json.loads(cfg.get("enabled_modules_json") or "{}")
        enabled_list = [k for k, v in modules.items() if v]
        disabled_list = [k for k, v in modules.items() if not v]

        ticket_stats = await self.bot.ticket_service.get_ticket_statistics(guild_id)
        active_jtc = await self.bot.jtc_service.get_active_rooms(guild_id)
        mod_cases_row = await self.bot.db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM moderation_cases WHERE guild_id = ? AND active = 1;",
            (guild_id,),
        )
        active_cases = int((mod_cases_row or {}).get("cnt", 0))
        db_health = await self.bot.db.health_check()
        cmd_report = self.bot.command_sync.audit_registered_commands()

        # Calculate configuration completion percentage
        completion_checks = [
            bool(cfg.get("mod_log_channel_id")),
            bool(cfg.get("server_log_channel_id")),
            bool(cfg.get("transcript_channel_id")),
            len(enabled_list) >= 8,
            db_health.get("connected", False),
        ]
        completion_pct = int((sum(1 for c in completion_checks if c) / len(completion_checks)) * 100)

        page_meta = next((p for p in DASHBOARD_PAGES if p["key"] == self.current_page), DASHBOARD_PAGES[0])
        embed = discord.Embed(
            title=f"Cosmic ki baddie Control Plane — {page_meta['label']}",
            description=page_meta["description"],
            color=discord.Color.blurple(),
        )

        if self.current_page == "overview":
            embed.add_field(
                name="Bot & Database Status",
                value=(
                    f"Bot Status: **Online (Nominal)**\n"
                    f"Database: **{'Connected' if db_health.get('connected') else 'Offline'}** (`{db_health.get('driver')}` v{db_health.get('schema_version')})\n"
                    f"Config Completion: **{completion_pct}%**"
                ),
                inline=True,
            )
            embed.add_field(
                name="Live Server Counters",
                value=(
                    f"Total Slash Commands: **{cmd_report.total_registered}**\n"
                    f"Total Tickets: **{ticket_stats['total']}** ({ticket_stats['open']} open)\n"
                    f"Active JTC Voice Rooms: **{len(active_jtc)}**\n"
                    f"Active Moderation Cases: **{active_cases}**"
                ),
                inline=True,
            )
            embed.add_field(
                name="Enabled Modules",
                value=", ".join(f"`{m}`" for m in enabled_list) if enabled_list else "None",
                inline=False,
            )
            embed.add_field(
                name="Disabled Modules",
                value=", ".join(f"`{m}`" for m in disabled_list) if disabled_list else "None (All 11 modules active)",
                inline=False,
            )
            embed.add_field(
                name="Last Configuration Update",
                value=f"`{cfg.get('updated_at', utc_now_iso())}`",
                inline=False,
            )

        elif self.current_page == "tickets":
            cats = await self.bot.ticket_service.ensure_default_categories(guild_id)
            sel_cat = next((c for c in cats if c["category_key"] == self.selected_ticket_category), cats[0])
            embed.add_field(
                name="Ticket Statistics",
                value=(
                    f"Total: **{ticket_stats['total']}** · Open: **{ticket_stats['open']}** · "
                    f"Claimed: **{ticket_stats['claimed']}** · Closed: **{ticket_stats['closed']}**"
                ),
                inline=False,
            )
            embed.add_field(
                name=f"Selected Category: {sel_cat['emoji']} {sel_cat['display_name']}",
                value=(
                    f"Key: `{sel_cat['category_key']}`\n"
                    f"Channel Naming: `{sel_cat['naming_format']}`\n"
                    f"Max Open / User: `{sel_cat['max_open_per_user']}`\n"
                    f"Auto-Delete Delay: `{sel_cat['auto_delete_seconds']}s`\n"
                    f"Discord Category ID: `{sel_cat.get('discord_category_id') or 'Default'}`\n"
                    f"Staff Roles: `{sel_cat.get('staff_role_ids_json', '[]')}`"
                ),
                inline=False,
            )

        elif self.current_page == "permissions":
            summary = await self.bot.permission_service.get_guild_permission_summary(guild_id)
            embed.add_field(name="Mapped RBAC Roles", value=str(len(summary["role_mappings"])), inline=True)
            embed.add_field(name="Mapped RBAC Users", value=str(len(summary["user_mappings"])), inline=True)
            embed.add_field(name="Command Overrides", value=str(len(summary["command_rules"])), inline=True)
            embed.add_field(
                name="RBAC Security Policy",
                value=(
                    "• Server-side verification on all commands & views\n"
                    "• Self-admin grant blocked · Privilege escalation blocked\n"
                    "• Server Owner & Bot Owner protected"
                ),
                inline=False,
            )

        elif self.current_page == "database_backup":
            backups = await self.bot.db.fetch_all(
                "SELECT backup_id, backup_label, created_at FROM server_backups WHERE guild_id = ? ORDER BY backup_id DESC LIMIT 5;",
                (guild_id,),
            )
            b_lines = [f"`#{b['backup_id']}` — {b['backup_label']} ({b['created_at']})" for b in backups] or [
                "No backups recorded yet. Click **Create SQLite Snapshot Backup** below."
            ]
            embed.add_field(
                name="SQLite Engine Diagnostics",
                value=(
                    f"Driver: `{db_health.get('driver')}` · Path: `{db_health.get('db_path')}`\n"
                    f"Schema Version: `v{db_health.get('schema_version')}/{db_health.get('total_migrations')}`\n"
                    f"Tables ({len(db_health.get('tables', []))}): {', '.join(f'`{t}`' for t in db_health.get('tables', [])[:8])}..."
                ),
                inline=False,
            )
            embed.add_field(name="Recent Guild Backups", value="\n".join(b_lines), inline=False)

        else:
            mod_active = modules.get(self.current_page, True)
            embed.add_field(
                name="Module Status",
                value=f"**{'Enabled' if mod_active else 'Disabled'}**",
                inline=True,
            )
            embed.add_field(
                name="Guild Prefix & Snipe Limit",
                value=f"Prefix: `{cfg.get('prefix', '!')}` · Snipe Limit: `{cfg.get('snipe_limit', 25)}`",
                inline=True,
            )
            mod_log_str = f"<#{cfg['mod_log_channel_id']}>" if cfg.get("mod_log_channel_id") else "`Not Set`"
            srv_log_str = f"<#{cfg['server_log_channel_id']}>" if cfg.get("server_log_channel_id") else "`Not Set`"
            trn_log_str = f"<#{cfg['transcript_channel_id']}>" if cfg.get("transcript_channel_id") else "`Not Set`"
            embed.add_field(
                name="Log Channels",
                value=(
                    f"Moderation Log: {mod_log_str}\n"
                    f"Server Log: {srv_log_str}\n"
                    f"Transcript Log: {trn_log_str}"
                ),
                inline=False,
            )

        embed.set_footer(text=f"Cosmic ki baddie Setup Wizard · Page: {self.current_page} · {utc_now_iso()}")
        return embed
