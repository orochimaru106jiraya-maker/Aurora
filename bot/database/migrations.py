"""
Database schema migrations for Cosmic ki baddie.
Maintains versioned schema transitions in SQLite with foreign keys and indexes.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

logger = logging.getLogger("cosmic.database.migrations")

# Versioned SQL migrations: (version_number, description, list_of_sql_statements)
MIGRATIONS: List[Tuple[int, str, List[str]]] = [
    (
        1,
        "Initial core guild configuration and schema version tracking",
        [
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS guild_configs (
                guild_id INTEGER PRIMARY KEY,
                prefix TEXT NOT NULL DEFAULT '!',
                mod_log_channel_id INTEGER,
                server_log_channel_id INTEGER,
                transcript_channel_id INTEGER,
                snipe_limit INTEGER NOT NULL DEFAULT 25,
                enabled_modules_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """,
        ],
    ),
    (
        2,
        "RBAC permissions tables for roles, users, commands, and modules",
        [
            """
            CREATE TABLE IF NOT EXISTS rbac_role_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                permission_level TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(guild_id, role_id, permission_level)
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_rbac_roles_guild ON rbac_role_mappings(guild_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS rbac_user_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                permission_level TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(guild_id, user_id, permission_level)
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_rbac_users_guild ON rbac_user_mappings(guild_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS rbac_command_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                command_name TEXT NOT NULL,
                module_name TEXT NOT NULL,
                required_level TEXT NOT NULL DEFAULT 'everyone',
                allowed_role_ids_json TEXT NOT NULL DEFAULT '[]',
                allowed_user_ids_json TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(guild_id, command_name)
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_rbac_cmd_guild ON rbac_command_rules(guild_id, command_name);
            """,
            """
            CREATE TABLE IF NOT EXISTS rbac_module_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                module_name TEXT NOT NULL,
                required_level TEXT NOT NULL DEFAULT 'everyone',
                allowed_role_ids_json TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(guild_id, module_name)
            );
            """,
        ],
    ),
    (
        3,
        "Advanced Ticket System categories, active tickets, and transcripts",
        [
            """
            CREATE TABLE IF NOT EXISTS ticket_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                category_key TEXT NOT NULL,
                display_name TEXT NOT NULL,
                emoji TEXT NOT NULL DEFAULT '🎫',
                description TEXT NOT NULL,
                discord_category_id INTEGER,
                transcript_channel_id INTEGER,
                staff_role_ids_json TEXT NOT NULL DEFAULT '[]',
                naming_format TEXT NOT NULL DEFAULT 'ticket-{username}-{id}',
                max_open_per_user INTEGER NOT NULL DEFAULT 1,
                auto_delete_seconds INTEGER NOT NULL DEFAULT 300,
                form_fields_json TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 1,
                UNIQUE(guild_id, category_key)
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_ticket_cat_guild ON ticket_categories(guild_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                ticket_number INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                creator_id INTEGER NOT NULL,
                category_key TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                claimed_by_id INTEGER,
                closed_by_id INTEGER,
                close_reason TEXT,
                form_responses_json TEXT NOT NULL DEFAULT '{}',
                transcript_text TEXT,
                dm_creator_sent INTEGER NOT NULL DEFAULT 0,
                dm_staff_sent INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                closed_at TEXT
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_tickets_guild_status ON tickets(guild_id, status);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_tickets_channel ON tickets(channel_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_tickets_creator ON tickets(guild_id, creator_id, category_key, status);
            """,
        ],
    ),
    (
        4,
        "Moderation cases, warnings, and snipe/editsnipe caches",
        [
            """
            CREATE TABLE IF NOT EXISTS moderation_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                case_number INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                target_user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                duration_seconds INTEGER,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(guild_id, case_number)
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_mod_cases_guild_user ON moderation_cases(guild_id, target_user_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS snipe_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                author_name TEXT NOT NULL,
                event_type TEXT NOT NULL, -- 'delete' or 'edit'
                old_content TEXT NOT NULL,
                new_content TEXT,
                attachment_urls_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_snipe_channel ON snipe_messages(guild_id, channel_id, event_type);
            """,
        ],
    ),
    (
        5,
        "Join-to-Create (JTC) voice hubs and active temporary voice rooms",
        [
            """
            CREATE TABLE IF NOT EXISTS jtc_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                hub_name TEXT NOT NULL DEFAULT 'Default Hub',
                trigger_channel_id INTEGER NOT NULL,
                target_category_id INTEGER,
                naming_format TEXT NOT NULL DEFAULT '{username}''s Room',
                default_limit INTEGER NOT NULL DEFAULT 0,
                cooldown_seconds INTEGER NOT NULL DEFAULT 10,
                max_active_rooms INTEGER NOT NULL DEFAULT 25,
                enabled INTEGER NOT NULL DEFAULT 1,
                UNIQUE(guild_id, trigger_channel_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS jtc_active_rooms (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                hub_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL,
                is_locked INTEGER NOT NULL DEFAULT 0,
                is_hidden INTEGER NOT NULL DEFAULT 0,
                user_limit INTEGER NOT NULL DEFAULT 0,
                allowed_users_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_jtc_rooms_guild ON jtc_active_rooms(guild_id);
            """,
        ],
    ),
    (
        6,
        "Activity-based auto roles, Reaction role panels, AI assistant, Auto-responder, Embed templates, Music queues, and Server Backups",
        [
            """
            CREATE TABLE IF NOT EXISTS activity_role_configs (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                spotify_role_id INTEGER,
                gaming_default_role_id INTEGER,
                gaming_map_json TEXT NOT NULL DEFAULT '{}',
                voice_default_role_id INTEGER,
                voice_channel_map_json TEXT NOT NULL DEFAULT '{}',
                chat_thresholds_json TEXT NOT NULL DEFAULT '[]',
                chat_cooldown_seconds INTEGER NOT NULL DEFAULT 30,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS activity_user_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                message_count INTEGER NOT NULL DEFAULT 0,
                last_message_at TEXT,
                UNIQUE(guild_id, user_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS reaction_role_panels (
                panel_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER,
                panel_title TEXT NOT NULL,
                panel_description TEXT NOT NULL,
                panel_mode TEXT NOT NULL DEFAULT 'buttons', -- 'buttons', 'dropdown', 'reactions'
                exclusive_group INTEGER NOT NULL DEFAULT 0,
                max_roles_per_user INTEGER NOT NULL DEFAULT 0,
                entries_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS ai_assistant_configs (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                mode TEXT NOT NULL DEFAULT 'local_kb', -- 'local_kb' or 'local_llm'
                personality TEXT NOT NULL DEFAULT 'Helpful, concise, and friendly Cosmic ki baddie server assistant.',
                response_style TEXT NOT NULL DEFAULT 'balanced',
                greeting_template TEXT NOT NULL DEFAULT 'Hello {user}! How can I help you today?',
                allowed_channel_ids_json TEXT NOT NULL DEFAULT '[]',
                allowed_role_ids_json TEXT NOT NULL DEFAULT '[]',
                cooldown_seconds INTEGER NOT NULL DEFAULT 5,
                max_history_turns INTEGER NOT NULL DEFAULT 6
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS ai_knowledge_entries (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                topic TEXT NOT NULL,
                keywords_json TEXT NOT NULL DEFAULT '[]',
                response_text TEXT NOT NULL,
                intent_category TEXT NOT NULL DEFAULT 'faq',
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(guild_id, topic)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS auto_responders (
                trigger_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                trigger_phrase TEXT NOT NULL,
                match_mode TEXT NOT NULL DEFAULT 'partial', -- 'exact' or 'partial'
                case_sensitive INTEGER NOT NULL DEFAULT 0,
                responses_json TEXT NOT NULL DEFAULT '[]',
                use_embed INTEGER NOT NULL DEFAULT 0,
                mention_user INTEGER NOT NULL DEFAULT 1,
                cooldown_seconds INTEGER NOT NULL DEFAULT 10,
                allowed_channels_json TEXT NOT NULL DEFAULT '[]',
                allowed_roles_json TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 1,
                UNIQUE(guild_id, trigger_phrase)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS embed_templates (
                template_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                template_name TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                color_hex TEXT NOT NULL DEFAULT '#6366F1',
                author_name TEXT NOT NULL DEFAULT '',
                author_icon_url TEXT NOT NULL DEFAULT '',
                footer_text TEXT NOT NULL DEFAULT '',
                thumbnail_url TEXT NOT NULL DEFAULT '',
                image_url TEXT NOT NULL DEFAULT '',
                fields_json TEXT NOT NULL DEFAULT '[]',
                include_timestamp INTEGER NOT NULL DEFAULT 1,
                created_by_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(guild_id, template_name)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS music_saved_queues (
                guild_id INTEGER PRIMARY KEY,
                queue_json TEXT NOT NULL DEFAULT '[]',
                volume INTEGER NOT NULL DEFAULT 80,
                loop_mode TEXT NOT NULL DEFAULT 'off',
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS server_backups (
                backup_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                backup_label TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_by_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """,
        ],
    ),
]
