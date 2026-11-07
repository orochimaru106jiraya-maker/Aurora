# Cosmic ki baddie (Project Aurora) — Advanced Discord Server Management Bot

**Cosmic ki baddie** (`Project Aurora`) is a production-grade, modular Discord server management platform built with **Python 3.11+**, **discord.py 2.x**, and **SQLite (`aiosqlite`)**. It is engineered for zero-code in-Discord server administration, featuring a 14-page interactive Setup Wizard, a 4-category Ticket Management Platform with automated transcripts and DM notifications, centralized Role-Based Access Control (RBAC), Join-to-Create (JTC) temporary voice channels, Activity-Based Auto Roles, Reaction Role panels, a zero-API-key Local AI Assistant, FFmpeg/PyNaCl Music playback, an Embed Builder, and an Auto-Responder.

---

## 1. Architecture Overview

```text
cosmic-ki-baddie/
├── main.py                         # Entrypoint, CLI verification (--verify-only), and Gateway runner
├── requirements.txt                # Production Python dependencies (discord.py[voice], aiosqlite, PyNaCl, yt-dlp, pytest)
├── railway.json                    # Railway Nixpacks configuration (Python 3.11, FFmpeg, libsodium, libopus)
├── .env.example                    # Environment variable template (Zero hardcoded secrets)
├── README.md                       # Complete Command Registry, Railway Deployment, and Developer Portal Guide
├── bot/
│   ├── core/
│   │   ├── bot.py                  # CosmicBot subclass wiring DB, services, Cogs, and persistent views
│   │   ├── config.py               # Environment config loader & structured file/console logging
│   │   ├── loader.py               # Deterministic 12-Cog loader with failure reporting
│   │   ├── command_sync.py         # Slash Command tree auditor, conflict detector & Discord sync
│   │   ├── error_handler.py        # Global app_commands error & RBAC/Hierarchy violation handler
│   │   ├── health.py               # Real-time command, extension, permission & SQLite health monitor
│   │   └── discord_compat.py       # discord.py 2.x runtime export + offline CI verification shim
│   ├── database/
│   │   ├── manager.py              # Centralized async SQLite manager (WAL mode, transactions, backups)
│   │   ├── migrations.py           # 6 versioned schema migrations (15 tables + indexes)
│   │   └── models.py               # Typed domain models, PermissionLevels & 4 default ticket categories
│   ├── services/
│   │   ├── permission_service.py   # Server-side RBAC engine, anti-escalation & self-admin guard
│   │   ├── ticket_service.py       # 4-category ticket lifecycle, transcript generator & DM pipeline
│   │   ├── jtc_service.py          # Join-to-Create temporary voice channel manager & restart recovery
│   │   ├── ai_service.py           # Mode A Local Knowledge Base / Intent AI + Mode B Optional Local LLM
│   │   ├── music_service.py        # Async-safe music queue, URL validator & FFmpeg/PyNaCl diagnostics
│   │   └── logging_service.py      # Guild settings, numbered moderation cases & snipe/editsnipe cache
│   ├── cogs/
│   │   ├── setup_wizard.py         # /setup (14-page dashboard) & /help (interactive command explorer)
│   │   ├── permissions.py          # /permissions suite (RBAC role/user/command/module management)
│   │   ├── tickets.py              # /jticket suite (16 commands + 4 categories + transcript DMs)
│   │   ├── moderation.py           # 19 moderation commands + hierarchy checks + snipe/editsnipe
│   │   ├── jtc.py                  # /jtc suite (16 commands + voice state listeners)
│   │   ├── activity_roles.py       # /activity suite (Spotify, Gaming, Voice, Text Chat auto-roles)
│   │   ├── reaction_roles.py       # /reactionrole suite (Buttons, Dropdowns, Reactions, Exclusive groups)
│   │   ├── ai_assistant.py         # /ai suite (10 commands + @mention listener)
│   │   ├── music.py                # 14 music commands (/play, /queue, /loop, /musicdiagnostics, etc.)
│   │   ├── embeds.py               # /embed suite (Create, edit, preview, publish, save, list, delete)
│   │   ├── auto_responder.py       # /autoresponder suite (Exact/partial triggers, cooldowns, tests)
│   │   └── administration.py       # 11 server administration, backup, restore & diagnostic commands
│   ├── ui/
│   │   ├── dashboard.py            # 14-page interactive Setup & Server Management View
│   │   ├── pagination.py           # Reusable PaginatedEmbedView
│   │   ├── confirmations.py        # Author-locked ConfirmationView for destructive actions
│   │   └── persistent_views.py     # Restart-safe Views (Ticket Panel, Ticket Controls, JTC, Reaction Roles)
│   └── utils/
│       ├── checks.py               # @require_permission_level decorator wired to PermissionService
│       ├── formatting.py           # Duration parser, channel slug sanitizer, UTC timestamps
│       └── validators.py           # Role hierarchy validator, assignable role check, hex/URL validators
└── tests/
    ├── test_database.py            # SQLite connection, migrations, atomic rollback, backup/restore tests
    ├── test_commands.py            # 12 Cogs, 126 registered Slash Commands, 14-page dashboard tests
    ├── test_permissions.py         # RBAC anti-escalation, self-admin block, owner protection, hierarchy tests
    ├── test_tickets.py             # 4 categories, duplicate prevention, claim/close transcript & DM tests
    ├── test_jtc.py                 # JTC voice room creation, ownership enforcement & empty room cleanup tests
    ├── test_music.py               # URL validation, queue lifecycle, pause/resume/skip/volume/loop tests
    └── test_ai.py                  # Local Knowledge Base matching, intent classification & auto-responder tests
```

---

## 2. Complete Slash Command Registry (126 Commands across 12 Cogs)

### Setup & Help (`bot.cogs.setup_wizard`)
- `/setup` — Launch the 14-page interactive server configuration dashboard.
- `/help` — Interactive paginated command directory and live command health check.

### Ticket System (`/jticket` — `bot.cogs.tickets`)
- `/jticket setup` — Open the interactive Ticket System setup page for all 4 categories.
- `/jticket panel` — Publish the persistent 4-category ticket creation panel (`General Help`, `File a Complaint`, `Apply for a Staff Role`, `Claim Winning Prize`).
- `/jticket config` — Configure category channel, staff role, transcript channel, limits, retention period, and naming format.
- `/jticket open` — Open a new ticket channel in one of the 4 categories.
- `/jticket close` — Close the ticket, generate transcript, archive to transcript channel, and DM the creator & claiming/closing moderator.
- `/jticket reopen` — Reopen a closed ticket and restore creator permissions.
- `/jticket delete` — Delete a ticket channel after recording status in SQLite.
- `/jticket claim` — Claim responsibility for the current ticket.
- `/jticket unclaim` — Release claim on the current ticket.
- `/jticket transfer` — Transfer ticket claim to another staff member.
- `/jticket add` — Grant a user access to the current ticket channel.
- `/jticket remove` — Revoke a user's access from the current ticket channel.
- `/jticket rename` — Rename the current ticket channel.
- `/jticket transcript` — Generate and download a complete `.txt` transcript of the ticket.
- `/jticket stats` — Display server ticket statistics across all 4 categories.
- `/jticket list` — List all currently open or claimed tickets.

### Moderation (`bot.cogs.moderation`)
- `/ban`, `/unban`, `/kick`, `/timeout`, `/untimeout`, `/warn`, `/warnings`, `/clearwarnings`, `/purge`, `/snipe`, `/editsnipe`, `/lock`, `/unlock`, `/slowmode`, `/hide`, `/unhide`, `/modlogs`, `/case`, `/clearcases`

### RBAC & Permissions (`/permissions` — `bot.cogs.permissions`)
- `/permissions setup`, `/permissions view`, `/permissions role add`, `/permissions role remove`, `/permissions user add`, `/permissions user remove`, `/permissions command`, `/permissions module`, `/permissions reset`

### Join-to-Create Voice (`/jtc` — `bot.cogs.jtc`)
- `/jtc setup`, `/jtc config`, `/jtc enable`, `/jtc disable`, `/jtc panel`, `/jtc list`, `/jtc rename`, `/jtc limit`, `/jtc lock`, `/jtc unlock`, `/jtc hide`, `/jtc unhide`, `/jtc add`, `/jtc remove`, `/jtc transfer`, `/jtc delete`

### Activity-Based Auto Roles (`/activity` — `bot.cogs.activity_roles`)
- `/activity setup`, `/activity config`, `/activity spotify`, `/activity gaming`, `/activity voice`, `/activity chat`, `/activity roles`, `/activity disable`

### Reaction Roles (`/reactionrole` — `bot.cogs.reaction_roles`)
- `/reactionrole setup`, `/reactionrole create`, `/reactionrole edit`, `/reactionrole delete`, `/reactionrole list`, `/reactionrole add`, `/reactionrole remove`

### Personal AI Assistant (`/ai` — `bot.cogs.ai_assistant`)
- `/ai setup`, `/ai enable`, `/ai disable`, `/ai personality`, `/ai knowledge add`, `/ai knowledge edit`, `/ai knowledge remove`, `/ai knowledge list`, `/ai reset`, `/ai status`

### Music System (`bot.cogs.music`)
- `/play`, `/pause`, `/resume`, `/skip`, `/stop`, `/queue`, `/nowplaying`, `/volume`, `/loop`, `/shuffle`, `/remove`, `/clearqueue`, `/disconnect`, `/musicdiagnostics`

### Custom Embed Builder (`/embed` — `bot.cogs.embeds`)
- `/embed create`, `/embed edit`, `/embed preview`, `/embed publish`, `/embed save`, `/embed list`, `/embed delete`

### Auto Responder (`/autoresponder` — `bot.cogs.auto_responder`)
- `/autoresponder create`, `/autoresponder edit`, `/autoresponder delete`, `/autoresponder list`, `/autoresponder enable`, `/autoresponder disable`, `/autoresponder test`

### Server Administration (`bot.cogs.administration`)
- `/serverinfo`, `/userinfo`, `/roleinfo`, `/channelinfo`, `/botinfo`, `/settings`, `/dashboard`, `/backup`, `/restore`, `/logs`, `/prefix`

---

## 3. Discord Developer Portal Configuration Guide

1. Visit the **Discord Developer Portal** (`https://discord.com/developers/applications`) and click **New Application** → name it **Cosmic ki baddie**.
2. Navigate to the **Bot** tab:
   - Enable all three **Privileged Gateway Intents**:
     - `PRESENCE INTENT` (Required for `/activity spotify` and `/activity gaming`)
     - `SERVER MEMBERS INTENT` (Required for RBAC role hierarchy and member lookups)
     - `MESSAGE CONTENT INTENT` (Required for `/autoresponder`, `/snipe`, `/editsnipe`, and `/activity chat`)
3. Navigate to **OAuth2 → URL Generator**:
   - Scopes: Check `bot` and `applications.commands`.
   - Bot Permissions: Check `Administrator` (or granular permissions: `Manage Roles`, `Manage Channels`, `Kick Members`, `Ban Members`, `Moderate Members`, `Manage Messages`, `View Channels`, `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History`, `Connect`, `Speak`, `Move Members`).
4. Copy the generated invite URL, invite **Cosmic ki baddie** to your server, and ensure the bot's role is dragged near the top of **Server Settings → Roles** so it sits above all roles it manages.

---

## 4. Railway Deployment & Persistent Volume Guide

### Step 1: Repository & Nixpacks Build
`railway.json` is pre-configured to use **Nixpacks** with `python311`, `ffmpeg`, `libsodium`, and `libopus` installed automatically for voice and music playback, with start command `python3 main.py`.

### Step 2: Persistent Volume Configuration (Critical for SQLite)
Because Railway containers have ephemeral filesystems across redeployments:
1. In your Railway Project Canvas, right-click your service → **Attach Volume**.
2. Set the **Mount Path** to `/data`.
3. In the service **Variables** tab, set:
   ```env
   DISCORD_BOT_TOKEN=your_actual_bot_token
   DISCORD_APPLICATION_ID=your_application_id
   BOT_OWNER_ID=your_discord_user_id
   DATABASE_PATH=/data/cosmic_baddie.db
   LOG_FILE_PATH=/data/cosmic_baddie.log
   ```

### Step 3: Resource Requirements & Plan Limitations
- **Baseline Bot + SQLite + Local Knowledge Base AI (Mode A)**: Uses **~65 MB – 110 MB RAM** and `< 0.1 vCPU`. Runs smoothly on Railway's Hobby ($5/mo) plan.
- **Voice & FFmpeg Audio Transcoding**: Each active guild music stream spawns an `ffmpeg` subprocess consuming **~35 MB – 60 MB RAM**.
- **Local LLM (Mode B)**: Hosting an external Ollama/Llama.cpp container requires **2 GB – 4 GB+ RAM**. On standard Railway plans, keep `LOCAL_LLM_ENDPOINT` empty so the bot uses **Mode A** (instant, deterministic SQLite Knowledge Base + Intent Classifier).

---

## 5. Automated Testing & Verification

Run the offline command registry verifier and automated test suite at any time:

```bash
# 1. Verify database migrations, load all 12 Cogs, and audit all 126 Slash Commands
python3 main.py --verify-only

# 2. Run the full automated test suite
python3 -m unittest discover -s tests -v
```
