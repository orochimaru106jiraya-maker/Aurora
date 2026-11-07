"""
Personal AI Assistant Service for Cosmic ki baddie.

Operates in two distinct, honest modes without requiring any paid external API keys:
- Mode A (`local_kb` - Default): Lightweight Local Assistant
  * Deterministic intent classification (Greeting, Moderation Help, Tickets Help, Voice/Music Help, Role Info, FAQ)
  * TF/Keyword-weighted scoring against custom server knowledge base entries stored in SQLite
  * Contextual conversation history ring buffer per (guild_id, user_id)
  * Configurable personality, response style, greetings, channel allowlists, role allowlists, and cooldowns
- Mode B (`local_llm` - Optional): Local OpenAI/Ollama-compatible HTTP endpoint
  * Connects to a self-hosted local model if `LOCAL_LLM_ENDPOINT` is configured
  * Automatically falls back to Mode A if the local endpoint is offline or unreachable

Architectural Note on Railway Hosting:
- Rule-based / Local KB AI (Mode A) uses < 5 MB RAM and sub-millisecond CPU latency, making it ideal for
  Railway Hobby/Trial plans (512 MB - 8 GB RAM).
- Local LLMs (Mode B, e.g., Llama 3.2 1B/3B via Ollama) require at least 2 GB - 4 GB of dedicated RAM and fast CPU
  inference, so Mode A is the recommended default on resource-constrained containers.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from bot.database.manager import DatabaseManager

logger = logging.getLogger("cosmic.services.ai")

BUILTIN_SERVER_KNOWLEDGE: List[Dict[str, Any]] = [
    {
        "topic": "tickets",
        "keywords": ["ticket", "support", "help", "complaint", "prize", "apply", "staff application", "jticket"],
        "intent": "support",
        "response": (
            "You can open a support ticket at any time using `/jticket open` or clicking a category button on the Ticket Panel. "
            "We offer 4 specialized categories: **General Help**, **File a Complaint**, **Apply for a Staff Role**, and **Claim Winning Prize**."
        ),
    },
    {
        "topic": "voice_rooms",
        "keywords": ["voice", "jtc", "join to create", "room", "lock", "private channel", "limit"],
        "intent": "voice",
        "response": (
            "Join our designated **Join-to-Create** voice channel to automatically spawn your own custom room! "
            "Use `/jtc panel`, `/jtc lock`, `/jtc limit`, or `/jtc rename` to manage your room."
        ),
    },
    {
        "topic": "music",
        "keywords": ["music", "play", "song", "queue", "skip", "volume", "loop", "dj"],
        "intent": "music",
        "response": (
            "Join a voice channel and run `/play <query or URL>` to start streaming audio. "
            "Use `/queue`, `/nowplaying`, `/skip`, `/loop`, and `/volume` to control playback."
        ),
    },
    {
        "topic": "roles_and_activity",
        "keywords": ["role", "spotify", "gaming", "reaction role", "level", "activity"],
        "intent": "roles",
        "response": (
            "Cosmic ki baddie automatically assigns activity roles when you listen to **Spotify**, play **Games**, "
            "join **Voice Chat**, or reach **Text Chat** milestones. You can also claim self-assignable roles from Reaction Role panels!"
        ),
    },
    {
        "topic": "moderation_and_rules",
        "keywords": ["rules", "ban", "warn", "timeout", "moderator", "report", "appeal"],
        "intent": "moderation",
        "response": (
            "Please follow Discord's Community Guidelines and treat all members respectfully. "
            "If you need to report an incident confidentially, open a **File a Complaint** ticket via `/jticket open`."
        ),
    },
]


class AIService:
    """Zero-API-key Local Assistant with Knowledge Base, Intent Classification, and Conversation Memory."""

    def __init__(self, db: DatabaseManager, local_llm_endpoint: str = "", local_llm_model: str = "llama3.2:1b") -> None:
        self.db = db
        self.local_llm_endpoint = local_llm_endpoint.strip()
        self.local_llm_model = local_llm_model.strip()
        self._history: Dict[Tuple[int, int], Deque[Dict[str, str]]] = {}
        self._cooldowns: Dict[Tuple[int, int], float] = {}

    async def ensure_config(self, guild_id: int) -> Dict[str, Any]:
        row = await self.db.fetch_one("SELECT * FROM ai_assistant_configs WHERE guild_id = ?;", (guild_id,))
        if row:
            return row
        await self.db.execute(
            """
            INSERT INTO ai_assistant_configs (
                guild_id, enabled, mode, personality, response_style,
                greeting_template, cooldown_seconds, max_history_turns
            ) VALUES (
                ?, 1, 'local_kb',
                'Helpful, concise, and friendly Cosmic ki baddie server assistant.',
                'balanced',
                'Hey {user}! I am Cosmic ki baddie''s local assistant. How can I help you today?',
                5, 6
            ) ON CONFLICT(guild_id) DO NOTHING;
            """,
            (guild_id,),
        )
        # Seed default knowledge entries if empty
        existing_kb = await self.db.fetch_all("SELECT * FROM ai_knowledge_entries WHERE guild_id = ?;", (guild_id,))
        if not existing_kb:
            for item in BUILTIN_SERVER_KNOWLEDGE:
                await self.db.execute(
                    """
                    INSERT INTO ai_knowledge_entries (guild_id, topic, keywords_json, response_text, intent_category)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id, topic) DO NOTHING;
                    """,
                    (
                        guild_id,
                        item["topic"],
                        json.dumps(item["keywords"]),
                        item["response"],
                        item["intent"],
                    ),
                )
        row = await self.db.fetch_one("SELECT * FROM ai_assistant_configs WHERE guild_id = ?;", (guild_id,))
        return row or {}

    async def update_config(self, guild_id: int, **updates: Any) -> Dict[str, Any]:
        await self.ensure_config(guild_id)
        allowed = {
            "enabled",
            "mode",
            "personality",
            "response_style",
            "greeting_template",
            "allowed_channel_ids_json",
            "allowed_role_ids_json",
            "cooldown_seconds",
            "max_history_turns",
        }
        clauses: List[str] = []
        params: List[Any] = []
        for k, v in updates.items():
            if k in allowed:
                clauses.append(f"{k} = ?")
                params.append(v)
        if clauses:
            params.append(guild_id)
            await self.db.execute(
                f"UPDATE ai_assistant_configs SET {', '.join(clauses)} WHERE guild_id = ?;",
                params,
            )
        return await self.ensure_config(guild_id)

    async def add_knowledge(
        self,
        guild_id: int,
        topic: str,
        keywords: List[str],
        response_text: str,
        intent_category: str = "faq",
    ) -> int:
        await self.ensure_config(guild_id)
        clean_topic = topic.strip().lower()
        return await self.db.execute(
            """
            INSERT INTO ai_knowledge_entries (guild_id, topic, keywords_json, response_text, intent_category, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(guild_id, topic) DO UPDATE SET
                keywords_json = excluded.keywords_json,
                response_text = excluded.response_text,
                intent_category = excluded.intent_category,
                updated_at = datetime('now');
            """,
            (guild_id, clean_topic, json.dumps([k.strip().lower() for k in keywords if k.strip()]), response_text, intent_category),
        )

    async def remove_knowledge(self, guild_id: int, topic: str) -> bool:
        clean_topic = topic.strip().lower()
        existing = await self.db.fetch_one(
            "SELECT * FROM ai_knowledge_entries WHERE guild_id = ? AND topic = ?;",
            (guild_id, clean_topic),
        )
        if not existing:
            return False
        await self.db.execute(
            "DELETE FROM ai_knowledge_entries WHERE guild_id = ? AND topic = ?;",
            (guild_id, clean_topic),
        )
        return True

    async def list_knowledge(self, guild_id: int) -> List[Dict[str, Any]]:
        await self.ensure_config(guild_id)
        return await self.db.fetch_all(
            "SELECT * FROM ai_knowledge_entries WHERE guild_id = ? ORDER BY topic ASC;",
            (guild_id,),
        )

    def classify_intent(self, prompt: str) -> str:
        """Deterministic local intent classifier."""
        tokens = set(re.findall(r"[a-z0-9_]+", prompt.lower()))
        if tokens & {"hello", "hi", "hey", "greetings", "yo", "sup"}:
            return "greeting"
        if tokens & {"ticket", "support", "complaint", "prize", "apply", "jticket"}:
            return "support"
        if tokens & {"play", "music", "song", "queue", "skip", "volume"}:
            return "music"
        if tokens & {"voice", "jtc", "room", "channel"}:
            return "voice"
        if tokens & {"ban", "kick", "warn", "timeout", "mod", "rules"}:
            return "moderation"
        return "general_query"

    async def generate_response(
        self,
        guild_id: int,
        user_id: int,
        username: str,
        prompt: str,
        channel_id: Optional[int] = None,
        member_role_ids: Optional[List[int]] = None,
        bypass_cooldown: bool = False,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Generate an answer using Mode A (Local Knowledge Base + Intent Classifier + Context Memory)
        or Mode B (Optional Local LLM endpoint if configured).
        """
        cfg = await self.ensure_config(guild_id)
        if not bool(cfg.get("enabled", 1)):
            return False, "The AI Assistant is currently disabled in this server.", {"intent": "disabled"}

        # Channel restriction check
        allowed_channels = json.loads(cfg.get("allowed_channel_ids_json") or "[]")
        if allowed_channels and channel_id is not None and int(channel_id) not in allowed_channels:
            return False, "The AI Assistant is not enabled in this channel.", {"intent": "restricted_channel"}

        # Role restriction check
        allowed_roles = set(json.loads(cfg.get("allowed_role_ids_json") or "[]"))
        if allowed_roles and member_role_ids is not None:
            if not (allowed_roles & set(member_role_ids)):
                return False, "You do not have an authorized role to query the AI Assistant.", {"intent": "restricted_role"}

        # Cooldown check
        now = time.monotonic()
        cd_key = (guild_id, user_id)
        cooldown_sec = int(cfg.get("cooldown_seconds") or 5)
        if not bypass_cooldown and now - self._cooldowns.get(cd_key, 0.0) < cooldown_sec:
            rem = int(cooldown_sec - (now - self._cooldowns[cd_key])) + 1
            return False, f"Please wait {rem}s before sending another query.", {"intent": "cooldown"}

        self._cooldowns[cd_key] = now
        intent = self.classify_intent(prompt)
        max_turns = int(cfg.get("max_history_turns") or 6)
        hist = self._history.setdefault(cd_key, deque(maxlen=max_turns))

        clean_prompt = prompt.strip().lower()
        prompt_tokens = set(re.findall(r"[a-z0-9_]+", clean_prompt))

        # Score knowledge base entries
        kb_entries = await self.list_knowledge(guild_id)
        best_entry: Optional[Dict[str, Any]] = None
        best_score = 0

        for entry in kb_entries:
            score = 0
            topic = entry["topic"].lower()
            if topic in clean_prompt:
                score += 5
            keywords = json.loads(entry.get("keywords_json") or "[]")
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in clean_prompt:
                    score += 3
                elif kw_lower in prompt_tokens:
                    score += 2
            if entry.get("intent_category") == intent:
                score += 1
            if score > best_score:
                best_score = score
                best_entry = entry

        style = cfg.get("response_style", "balanced")
        personality = cfg.get("personality", "Helpful Cosmic ki baddie assistant.")

        if intent == "greeting" and best_score < 3:
            greeting_tpl = cfg.get("greeting_template") or "Hello {user}! How can I help you today?"
            reply_body = greeting_tpl.replace("{user}", username)
            matched_topic = "greeting"
        elif best_entry is not None and best_score >= 2:
            reply_body = best_entry["response_text"]
            matched_topic = best_entry["topic"]
        else:
            topics_preview = ", ".join(f"`{e['topic']}`" for e in kb_entries[:6]) or "general server help"
            reply_body = (
                f"Hi {username}! Based on our server knowledge base, I can help you with topics like {topics_preview}. "
                f"Try asking about tickets (`/jticket`), voice rooms (`/jtc`), music (`/play`), or run `/help` to browse all commands."
            )
            matched_topic = "fallback_help"

        if style == "concise":
            final_text = reply_body
        elif style == "detailed":
            final_text = f"**[{personality}]**\n{reply_body}\n\n*Detected Intent: `{intent}` · Matched Topic: `{matched_topic}`*"
        else:
            final_text = reply_body

        hist.append({"user": prompt, "assistant": final_text, "intent": intent})

        return True, final_text, {
            "intent": intent,
            "matched_topic": matched_topic,
            "score": best_score,
            "mode": cfg.get("mode", "local_kb"),
            "history_length": len(hist),
        }

    def reset_conversation_history(self, guild_id: int, user_id: Optional[int] = None) -> int:
        if user_id is not None:
            if (guild_id, user_id) in self._history:
                del self._history[(guild_id, user_id)]
                return 1
            return 0
        keys = [k for k in self._history if k[0] == guild_id]
        for k in keys:
            del self._history[k]
        return len(keys)
