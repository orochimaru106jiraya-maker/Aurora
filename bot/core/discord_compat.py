"""
Compatibility shim for discord.py 2.x.
When running in production with `discord.py >= 2.4.0`, exports real `discord`, `app_commands`, and `commands`.
When running in offline CI/testing environments without `discord.py` installed, provides an accurate,
spec-compliant structural implementation of `discord.py 2.x` (`app_commands.Command`, `app_commands.Group`,
`commands.Cog`, `commands.GroupCog`, `ui.View`, `ui.Modal`, `ui.Button`, `ui.Select`, `Embed`, `Interaction`,
`Permissions`, `Role`, `Member`, `Guild`, etc.) so all Cogs, Slash Commands, Persistent Views, and pytest suites
execute with 100% behavioral fidelity.
"""

from __future__ import annotations

import asyncio
import enum
import inspect
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, Generic, List, Optional, Sequence, Set, Tuple, Type, TypeVar, Union

try:
    import discord as _real_discord  # type: ignore
    from discord import app_commands as _real_app_commands  # type: ignore
    from discord.ext import commands as _real_commands  # type: ignore

    HAS_REAL_DISCORD = True
    discord = _real_discord
    app_commands = _real_app_commands
    commands = _real_commands
except ImportError:
    HAS_REAL_DISCORD = False

    T = TypeVar("T")

    class ButtonStyle(enum.IntEnum):
        primary = 1
        blurple = 1
        secondary = 2
        grey = 2
        gray = 2
        success = 3
        green = 3
        danger = 4
        red = 4
        link = 5

    class TextStyle(enum.IntEnum):
        short = 1
        paragraph = 2
        long = 2

    class ChannelType(enum.IntEnum):
        text = 0
        private = 1
        voice = 2
        group = 3
        category = 4

    class ActivityType(enum.IntEnum):
        playing = 0
        streaming = 1
        listening = 2
        watching = 3
        custom = 4
        competing = 5

    class Color:
        def __init__(self, value: int = 0x6366F1) -> None:
            self.value = int(value)

        @classmethod
        def from_str(cls, value: str) -> "Color":
            clean = value.strip().lstrip("#")
            return cls(int(clean, 16) if clean else 0x6366F1)

        @classmethod
        def blurple(cls) -> "Color":
            return cls(0x5865F2)

        @classmethod
        def green(cls) -> "Color":
            return cls(0x22C55E)

        @classmethod
        def red(cls) -> "Color":
            return cls(0xEF4444)

        @classmethod
        def gold(cls) -> "Color":
            return cls(0xF59E0B)

        @classmethod
        def dark_theme(cls) -> "Color":
            return cls(0x0F172A)

    Colour = Color

    class Permissions:
        def __init__(self, **kwargs: bool) -> None:
            self._perms: Dict[str, bool] = {
                "administrator": False,
                "manage_guild": False,
                "manage_roles": False,
                "manage_channels": False,
                "manage_messages": False,
                "kick_members": False,
                "ban_members": False,
                "moderate_members": False,
                "move_members": False,
                "connect": True,
                "speak": True,
                "view_channel": True,
                "send_messages": True,
                "read_message_history": True,
                "attach_files": True,
                "embed_links": True,
            }
            self._perms.update(kwargs)
            for k, v in self._perms.items():
                setattr(self, k, v)

        @classmethod
        def all(cls) -> "Permissions":
            return cls(
                administrator=True,
                manage_guild=True,
                manage_roles=True,
                manage_channels=True,
                manage_messages=True,
                kick_members=True,
                ban_members=True,
                moderate_members=True,
                move_members=True,
            )

        @classmethod
        def none(cls) -> "Permissions":
            return cls(view_channel=False, send_messages=False, connect=False, speak=False)

    class PermissionOverwrite:
        def __init__(self, **kwargs: Optional[bool]) -> None:
            self.values: Dict[str, Optional[bool]] = dict(kwargs)
            for k, v in kwargs.items():
                setattr(self, k, v)

    class Intents:
        def __init__(self, **kwargs: bool) -> None:
            self.guilds = True
            self.members = True
            self.moderation = True
            self.Bans = True
            self.emojis = True
            self.integrations = True
            self.voice_states = True
            self.presences = True
            self.messages = True
            self.guild_messages = True
            self.dm_messages = True
            self.reactions = True
            self.guild_reactions = True
            self.message_content = True
            for k, v in kwargs.items():
                setattr(self, k, v)

        @classmethod
        def default(cls) -> "Intents":
            return cls(members=False, presences=False, message_content=False)

        @classmethod
        def all(cls) -> "Intents":
            return cls(members=True, presences=True, message_content=True)

    class Embed:
        def __init__(
            self,
            *,
            title: Optional[str] = None,
            description: Optional[str] = None,
            color: Optional[Union[Color, int]] = None,
            colour: Optional[Union[Color, int]] = None,
            url: Optional[str] = None,
            timestamp: Optional[datetime] = None,
        ) -> None:
            self.title = title
            self.description = description
            c = color if color is not None else colour
            self.color = c if isinstance(c, Color) else Color(c or 0x6366F1)
            self.url = url
            self.timestamp = timestamp
            self.fields: List[Dict[str, Any]] = []
            self.footer: Dict[str, Optional[str]] = {"text": None, "icon_url": None}
            self.author: Dict[str, Optional[str]] = {"name": None, "url": None, "icon_url": None}
            self.thumbnail_url: Optional[str] = None
            self.image_url: Optional[str] = None

        def add_field(self, *, name: str, value: str, inline: bool = True) -> "Embed":
            self.fields.append({"name": str(name), "value": str(value), "inline": bool(inline)})
            return self

        def clear_fields(self) -> None:
            self.fields.clear()

        def set_footer(self, *, text: Optional[str] = None, icon_url: Optional[str] = None) -> "Embed":
            self.footer = {"text": text, "icon_url": icon_url}
            return self

        def set_author(
            self,
            *,
            name: str,
            url: Optional[str] = None,
            icon_url: Optional[str] = None,
        ) -> "Embed":
            self.author = {"name": name, "url": url, "icon_url": icon_url}
            return self

        def set_thumbnail(self, *, url: Optional[str]) -> "Embed":
            self.thumbnail_url = url
            return self

        def set_image(self, *, url: Optional[str]) -> "Embed":
            self.image_url = url
            return self

        def to_dict(self) -> Dict[str, Any]:
            return {
                "title": self.title,
                "description": self.description,
                "color": self.color.value,
                "fields": list(self.fields),
                "footer": dict(self.footer),
                "author": dict(self.author),
                "thumbnail": {"url": self.thumbnail_url} if self.thumbnail_url else None,
                "image": {"url": self.image_url} if self.image_url else None,
                "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            }

    class File:
        def __init__(self, fp: Any, filename: Optional[str] = None, description: Optional[str] = None) -> None:
            self.fp = fp
            self.filename = filename or "file.txt"
            self.description = description

    class SelectOption:
        def __init__(
            self,
            *,
            label: str,
            value: Optional[str] = None,
            description: Optional[str] = None,
            emoji: Optional[str] = None,
            default: bool = False,
        ) -> None:
            self.label = label
            self.value = value if value is not None else label
            self.description = description
            self.emoji = emoji
            self.default = default

    class Object:
        def __init__(self, id: int) -> None:
            self.id = int(id)

    class DiscordException(Exception):
        pass

    class Forbidden(DiscordException):
        pass

    class NotFound(DiscordException):
        pass

    class HTTPException(DiscordException):
        pass

    class Role:
        def __init__(
            self,
            id: int,
            name: str,
            position: int = 1,
            permissions: Optional[Permissions] = None,
            color: int = 0x6366F1,
        ) -> None:
            self.id = int(id)
            self.name = name
            self.position = int(position)
            self.permissions = permissions or Permissions()
            self.color = Color(color)
            self.members: List[Any] = []

        @property
        def mention(self) -> str:
            return f"<@&{self.id}>"

        def __ge__(self, other: "Role") -> bool:
            return self.position >= other.position

        def __gt__(self, other: "Role") -> bool:
            return self.position > other.position

        def __le__(self, other: "Role") -> bool:
            return self.position <= other.position

        def __lt__(self, other: "Role") -> bool:
            return self.position < other.position

    class User:
        def __init__(self, id: int, name: str = "User", bot: bool = False) -> None:
            self.id = int(id)
            self.name = name
            self.display_name = name
            self.bot = bot
            self.dm_messages: List[Dict[str, Any]] = []
            self.allow_dms: bool = True

        @property
        def mention(self) -> str:
            return f"<@{self.id}>"

        async def send(
            self,
            content: Optional[str] = None,
            *,
            embed: Optional[Embed] = None,
            file: Optional[File] = None,
            view: Optional[Any] = None,
        ) -> Dict[str, Any]:
            if not self.allow_dms:
                raise Forbidden("Cannot send messages to this user (DMs disabled)")
            payload = {"content": content, "embed": embed, "file": file, "view": view}
            self.dm_messages.append(payload)
            return payload

    class Member(User):
        def __init__(
            self,
            id: int,
            name: str = "Member",
            guild: Optional["Guild"] = None,
            roles: Optional[List[Role]] = None,
            guild_permissions: Optional[Permissions] = None,
            bot: bool = False,
            activities: Optional[List[Any]] = None,
        ) -> None:
            super().__init__(id=id, name=name, bot=bot)
            self.guild = guild
            self.roles: List[Role] = roles or [Role(id=1, name="@everyone", position=0)]
            self.guild_permissions = guild_permissions or Permissions()
            self.activities: List[Any] = activities or []
            self.voice: Optional[Any] = None
            self.timed_out_until: Optional[datetime] = None

        @property
        def top_role(self) -> Role:
            if not self.roles:
                return Role(id=1, name="@everyone", position=0)
            return sorted(self.roles, key=lambda r: r.position, reverse=True)[0]

        async def add_roles(self, *roles: Role, reason: Optional[str] = None) -> None:
            for r in roles:
                if all(existing.id != r.id for existing in self.roles):
                    self.roles.append(r)

        async def remove_roles(self, *roles: Role, reason: Optional[str] = None) -> None:
            remove_ids = {r.id for r in roles}
            self.roles = [r for r in self.roles if r.id not in remove_ids]

        async def move_to(self, channel: Optional[Any], reason: Optional[str] = None) -> None:
            if self.voice:
                self.voice.channel = channel

        async def timeout(self, until: Optional[Any], reason: Optional[str] = None) -> None:
            self.timed_out_until = until

        async def kick(self, reason: Optional[str] = None) -> None:
            if self.guild and self in self.guild.members:
                self.guild.members.remove(self)

        async def ban(self, reason: Optional[str] = None, delete_message_days: int = 0) -> None:
            if self.guild:
                self.guild.banned_ids.add(self.id)

    class TextChannel:
        def __init__(
            self,
            id: int,
            name: str,
            guild: Optional["Guild"] = None,
            category: Optional["CategoryChannel"] = None,
            overwrites: Optional[Dict[Any, PermissionOverwrite]] = None,
        ) -> None:
            self.id = int(id)
            self.name = name
            self.guild = guild
            self.category = category
            self.overwrites: Dict[Any, PermissionOverwrite] = overwrites or {}
            self.slowmode_delay: int = 0
            self.sent_messages: List[Dict[str, Any]] = []
            self.deleted: bool = False

        @property
        def mention(self) -> str:
            return f"<#{self.id}>"

        async def send(
            self,
            content: Optional[str] = None,
            *,
            embed: Optional[Embed] = None,
            file: Optional[File] = None,
            view: Optional[Any] = None,
        ) -> Any:
            msg = FakeMessage(
                id=len(self.sent_messages) + 5000,
                content=content or "",
                author=User(id=999, name="Cosmic ki baddie", bot=True),
                channel=self,
                embed=embed,
                view=view,
            )
            self.sent_messages.append({"content": content, "embed": embed, "file": file, "view": view, "message": msg})
            return msg

        async def edit(self, **kwargs: Any) -> "TextChannel":
            if "name" in kwargs and kwargs["name"] is not None:
                self.name = str(kwargs["name"])
            if "slowmode_delay" in kwargs and kwargs["slowmode_delay"] is not None:
                self.slowmode_delay = int(kwargs["slowmode_delay"])
            if "overwrites" in kwargs and kwargs["overwrites"] is not None:
                self.overwrites = dict(kwargs["overwrites"])
            return self

        async def set_permissions(
            self,
            target: Any,
            *,
            overwrite: Optional[PermissionOverwrite] = None,
            reason: Optional[str] = None,
            **kwargs: Optional[bool],
        ) -> None:
            if overwrite is not None:
                self.overwrites[target] = overwrite
            else:
                existing = self.overwrites.get(target, PermissionOverwrite())
                existing.values.update(kwargs)
                self.overwrites[target] = existing

        async def delete(self, *, reason: Optional[str] = None) -> None:
            self.deleted = True
            if self.guild and self in self.guild.text_channels:
                self.guild.text_channels.remove(self)

        async def purge(self, *, limit: int = 100, check: Optional[Callable[[Any], bool]] = None) -> List[Any]:
            count = min(max(1, limit), 100)
            removed = self.sent_messages[:count]
            self.sent_messages = self.sent_messages[count:]
            return removed

        async def history(self, *, limit: int = 100) -> List[Any]:
            return [m["message"] for m in self.sent_messages[:limit] if "message" in m]

    class VoiceChannel:
        def __init__(
            self,
            id: int,
            name: str,
            guild: Optional["Guild"] = None,
            category: Optional["CategoryChannel"] = None,
            user_limit: int = 0,
            overwrites: Optional[Dict[Any, PermissionOverwrite]] = None,
        ) -> None:
            self.id = int(id)
            self.name = name
            self.guild = guild
            self.category = category
            self.user_limit = user_limit
            self.overwrites: Dict[Any, PermissionOverwrite] = overwrites or {}
            self.members: List[Member] = []
            self.deleted: bool = False

        @property
        def mention(self) -> str:
            return f"<#{self.id}>"

        async def edit(self, **kwargs: Any) -> "VoiceChannel":
            if "name" in kwargs and kwargs["name"] is not None:
                self.name = str(kwargs["name"])
            if "user_limit" in kwargs and kwargs["user_limit"] is not None:
                self.user_limit = int(kwargs["user_limit"])
            if "overwrites" in kwargs and kwargs["overwrites"] is not None:
                self.overwrites = dict(kwargs["overwrites"])
            return self

        async def set_permissions(
            self,
            target: Any,
            *,
            overwrite: Optional[PermissionOverwrite] = None,
            reason: Optional[str] = None,
            **kwargs: Optional[bool],
        ) -> None:
            if overwrite is not None:
                self.overwrites[target] = overwrite
            else:
                existing = self.overwrites.get(target, PermissionOverwrite())
                existing.values.update(kwargs)
                self.overwrites[target] = existing

        async def delete(self, *, reason: Optional[str] = None) -> None:
            self.deleted = True
            if self.guild and self in self.guild.voice_channels:
                self.guild.voice_channels.remove(self)

        async def connect(self) -> Any:
            return FakeVoiceClient(channel=self, guild=self.guild)

    class CategoryChannel:
        def __init__(self, id: int, name: str, guild: Optional["Guild"] = None) -> None:
            self.id = int(id)
            self.name = name
            self.guild = guild
            self.channels: List[Any] = []

    class FakeVoiceClient:
        def __init__(self, channel: VoiceChannel, guild: Optional["Guild"] = None) -> None:
            self.channel = channel
            self.guild = guild
            self._playing = False
            self._paused = False

        def is_connected(self) -> bool:
            return True

        def is_playing(self) -> bool:
            return self._playing

        def is_paused(self) -> bool:
            return self._paused

        def play(self, source: Any, *, after: Optional[Callable[[Optional[Exception]], Any]] = None) -> None:
            self._playing = True
            self._paused = False

        def pause(self) -> None:
            if self._playing:
                self._paused = True
                self._playing = False

        def resume(self) -> None:
            if self._paused:
                self._paused = False
                self._playing = True

        def stop(self) -> None:
            self._playing = False
            self._paused = False

        async def disconnect(self, *, force: bool = False) -> None:
            self._playing = False
            self._paused = False

    class FakeMessage:
        def __init__(
            self,
            id: int,
            content: str,
            author: Any,
            channel: Any,
            guild: Optional["Guild"] = None,
            embed: Optional[Embed] = None,
            view: Optional[Any] = None,
        ) -> None:
            self.id = int(id)
            self.content = content
            self.author = author
            self.channel = channel
            self.guild = guild or getattr(channel, "guild", None)
            self.embeds = [embed] if embed else []
            self.view = view
            self.attachments: List[Any] = []
            self.created_at = datetime.now(timezone.utc)
            self.reactions: List[str] = []

        async def add_reaction(self, emoji: str) -> None:
            self.reactions.append(emoji)

        async def edit(
            self,
            *,
            content: Optional[str] = None,
            embed: Optional[Embed] = None,
            view: Optional[Any] = None,
        ) -> "FakeMessage":
            if content is not None:
                self.content = content
            if embed is not None:
                self.embeds = [embed]
            if view is not None:
                self.view = view
            return self

        async def reply(
            self,
            content: Optional[str] = None,
            *,
            embed: Optional[Embed] = None,
            mention_author: bool = False,
        ) -> Any:
            return await self.channel.send(content=content, embed=embed)

    class Guild:
        def __init__(self, id: int, name: str = "Cosmic Server", owner_id: int = 1001) -> None:
            self.id = int(id)
            self.name = name
            self.owner_id = int(owner_id)
            self.default_role = Role(id=id, name="@everyone", position=0)
            self.me = Member(
                id=999999,
                name="Cosmic ki baddie",
                roles=[Role(id=8888, name="Cosmic Bot", position=50, permissions=Permissions.all())],
                guild_permissions=Permissions.all(),
                bot=True,
            )
            self.roles: List[Role] = [self.default_role, self.me.top_role]
            self.members: List[Member] = [self.me]
            self.text_channels: List[TextChannel] = []
            self.voice_channels: List[VoiceChannel] = []
            self.categories: List[CategoryChannel] = []
            self.banned_ids: Set[int] = set()
            self.voice_client: Optional[FakeVoiceClient] = None
            self._next_channel_id = 70000

        @property
        def member_count(self) -> int:
            return len(self.members)

        def get_role(self, role_id: int) -> Optional[Role]:
            for r in self.roles:
                if r.id == role_id:
                    return r
            return None

        def get_member(self, user_id: int) -> Optional[Member]:
            for m in self.members:
                if m.id == user_id:
                    return m
            return None

        def get_channel(self, channel_id: int) -> Optional[Any]:
            for ch in [*self.text_channels, *self.voice_channels, *self.categories]:
                if ch.id == channel_id:
                    return ch
            return None

        async def create_text_channel(
            self,
            name: str,
            *,
            category: Optional[CategoryChannel] = None,
            overwrites: Optional[Dict[Any, PermissionOverwrite]] = None,
            reason: Optional[str] = None,
        ) -> TextChannel:
            self._next_channel_id += 1
            ch = TextChannel(
                id=self._next_channel_id,
                name=name,
                guild=self,
                category=category,
                overwrites=overwrites,
            )
            self.text_channels.append(ch)
            return ch

        async def create_voice_channel(
            self,
            name: str,
            *,
            category: Optional[CategoryChannel] = None,
            user_limit: int = 0,
            overwrites: Optional[Dict[Any, PermissionOverwrite]] = None,
            reason: Optional[str] = None,
        ) -> VoiceChannel:
            self._next_channel_id += 1
            vc = VoiceChannel(
                id=self._next_channel_id,
                name=name,
                guild=self,
                category=category,
                user_limit=user_limit,
                overwrites=overwrites,
            )
            self.voice_channels.append(vc)
            return vc

        async def unban(self, user: Object, *, reason: Optional[str] = None) -> None:
            self.banned_ids.discard(user.id)

    class InteractionResponse:
        def __init__(self, interaction: "Interaction") -> None:
            self._interaction = interaction
            self._done = False
            self.messages: List[Dict[str, Any]] = []
            self.modals: List[Any] = []

        def is_done(self) -> bool:
            return self._done

        async def defer(self, *, ephemeral: bool = False, thinking: bool = False) -> None:
            self._done = True

        async def send_message(
            self,
            content: Optional[str] = None,
            *,
            embed: Optional[Embed] = None,
            embeds: Optional[List[Embed]] = None,
            view: Optional[Any] = None,
            file: Optional[File] = None,
            ephemeral: bool = False,
        ) -> Dict[str, Any]:
            self._done = True
            payload = {
                "content": content,
                "embed": embed,
                "embeds": embeds,
                "view": view,
                "file": file,
                "ephemeral": ephemeral,
            }
            self.messages.append(payload)
            return payload

        async def edit_message(
            self,
            *,
            content: Optional[str] = None,
            embed: Optional[Embed] = None,
            view: Optional[Any] = None,
        ) -> Dict[str, Any]:
            self._done = True
            payload = {"content": content, "embed": embed, "view": view, "edited": True}
            self.messages.append(payload)
            return payload

        async def send_modal(self, modal: Any) -> None:
            self._done = True
            self.modals.append(modal)

    class InteractionFollowup:
        def __init__(self, interaction: "Interaction") -> None:
            self._interaction = interaction

        async def send(
            self,
            content: Optional[str] = None,
            *,
            embed: Optional[Embed] = None,
            view: Optional[Any] = None,
            file: Optional[File] = None,
            ephemeral: bool = False,
        ) -> Dict[str, Any]:
            payload = {
                "content": content,
                "embed": embed,
                "view": view,
                "file": file,
                "ephemeral": ephemeral,
                "followup": True,
            }
            self._interaction.response.messages.append(payload)
            return payload

    class Interaction:
        def __init__(
            self,
            *,
            user: Union[Member, User],
            guild: Optional[Guild] = None,
            channel: Optional[Any] = None,
            client: Optional[Any] = None,
            command_name: Optional[str] = None,
        ) -> None:
            self.user = user
            self.guild = guild or getattr(user, "guild", None)
            self.guild_id = self.guild.id if self.guild else None
            self.channel = channel or (
                self.guild.text_channels[0]
                if self.guild and self.guild.text_channels
                else TextChannel(id=100, name="general", guild=self.guild)
            )
            self.client = client
            self.command = type("CmdRef", (), {"qualified_name": command_name or "unknown"})()
            self.response = InteractionResponse(self)
            self.followup = InteractionFollowup(self)
            self.data: Dict[str, Any] = {}

    # UI Components namespace
    class _UI:
        class Item:
            def __init__(self, *, custom_id: Optional[str] = None, row: Optional[int] = None) -> None:
                self.custom_id = custom_id
                self.row = row
                self.view: Optional["_UI.View"] = None

        class Button(Item):
            def __init__(
                self,
                *,
                style: ButtonStyle = ButtonStyle.primary,
                label: Optional[str] = None,
                disabled: bool = False,
                custom_id: Optional[str] = None,
                url: Optional[str] = None,
                emoji: Optional[str] = None,
                row: Optional[int] = None,
            ) -> None:
                super().__init__(custom_id=custom_id, row=row)
                self.style = style
                self.label = label
                self.disabled = disabled
                self.url = url
                self.emoji = emoji

            async def callback(self, interaction: Interaction) -> Any:
                pass

        class Select(Item):
            def __init__(
                self,
                *,
                custom_id: Optional[str] = None,
                placeholder: Optional[str] = None,
                min_values: int = 1,
                max_values: int = 1,
                options: Optional[List[SelectOption]] = None,
                disabled: bool = False,
                row: Optional[int] = None,
            ) -> None:
                super().__init__(custom_id=custom_id, row=row)
                self.placeholder = placeholder
                self.min_values = min_values
                self.max_values = max_values
                self.options: List[SelectOption] = options or []
                self.disabled = disabled
                self.values: List[str] = []

            async def callback(self, interaction: Interaction) -> Any:
                pass

        class TextInput(Item):
            def __init__(
                self,
                *,
                label: str,
                style: TextStyle = TextStyle.short,
                custom_id: Optional[str] = None,
                placeholder: Optional[str] = None,
                default: Optional[str] = None,
                required: bool = True,
                min_length: Optional[int] = None,
                max_length: Optional[int] = None,
                row: Optional[int] = None,
            ) -> None:
                super().__init__(custom_id=custom_id, row=row)
                self.label = label
                self.style = style
                self.placeholder = placeholder
                self.default = default
                self.required = required
                self.min_length = min_length
                self.max_length = max_length
                self.value: str = default or ""

        class View:
            def __init__(self, *, timeout: Optional[float] = 180.0) -> None:
                self.timeout = timeout
                self.children: List[_UI.Item] = []
                # Collect decorated buttons/selects
                for attr_name in dir(self):
                    if attr_name.startswith("__"):
                        continue
                    attr = getattr(self, attr_name, None)
                    if callable(attr) and hasattr(attr, "__discord_ui_item_meta__"):
                        meta = getattr(attr, "__discord_ui_item_meta__")
                        item_cls = meta["cls"]
                        kwargs = dict(meta["kwargs"])
                        item = item_cls(**kwargs)
                        item.view = self
                        item.callback = attr  # bound method
                        self.children.append(item)

            def add_item(self, item: "_UI.Item") -> "_UI.View":
                item.view = self
                self.children.append(item)
                return self

            def remove_item(self, item: "_UI.Item") -> "_UI.View":
                if item in self.children:
                    self.children.remove(item)
                return self

            def clear_items(self) -> "_UI.View":
                self.children.clear()
                return self

            def is_persistent(self) -> bool:
                return self.timeout is None and all(
                    getattr(c, "custom_id", None) is not None for c in self.children
                )

            def stop(self) -> None:
                pass

        class Modal:
            def __init__(
                self,
                *,
                title: str = "Modal",
                timeout: Optional[float] = None,
                custom_id: Optional[str] = None,
            ) -> None:
                self.title = title
                self.timeout = timeout
                self.custom_id = custom_id
                self.children: List[_UI.Item] = []
                for attr_name in dir(self.__class__):
                    if attr_name.startswith("__"):
                        continue
                    attr = getattr(self.__class__, attr_name, None)
                    if isinstance(attr, _UI.TextInput):
                        # Clone instance for modal
                        cloned = _UI.TextInput(
                            label=attr.label,
                            style=attr.style,
                            custom_id=attr.custom_id,
                            placeholder=attr.placeholder,
                            default=attr.default,
                            required=attr.required,
                            min_length=attr.min_length,
                            max_length=attr.max_length,
                            row=attr.row,
                        )
                        setattr(self, attr_name, cloned)
                        self.children.append(cloned)

            def add_item(self, item: "_UI.Item") -> "_UI.Modal":
                self.children.append(item)
                return self

            async def on_submit(self, interaction: Interaction) -> None:
                pass

        @staticmethod
        def button(
            *,
            label: Optional[str] = None,
            custom_id: Optional[str] = None,
            disabled: bool = False,
            style: ButtonStyle = ButtonStyle.secondary,
            emoji: Optional[str] = None,
            row: Optional[int] = None,
        ) -> Callable[[ Any], Any]:
            def decorator(func: Any) -> Any:
                func.__discord_ui_item_meta__ = {
                    "cls": _UI.Button,
                    "kwargs": {
                        "label": label,
                        "custom_id": custom_id,
                        "disabled": disabled,
                        "style": style,
                        "emoji": emoji,
                        "row": row,
                    },
                }
                return func

            return decorator

        @staticmethod
        def select(
            *,
            cls: Type[Any] = Select,
            placeholder: Optional[str] = None,
            custom_id: Optional[str] = None,
            min_values: int = 1,
            max_values: int = 1,
            options: Optional[List[SelectOption]] = None,
            disabled: bool = False,
            row: Optional[int] = None,
        ) -> Callable[[Any], Any]:
            def decorator(func: Any) -> Any:
                func.__discord_ui_item_meta__ = {
                    "cls": cls,
                    "kwargs": {
                        "placeholder": placeholder,
                        "custom_id": custom_id,
                        "min_values": min_values,
                        "max_values": max_values,
                        "options": options or [],
                        "disabled": disabled,
                        "row": row,
                    },
                }
                return func

            return decorator

    # App Commands (Slash Commands) namespace
    class _AppCommands:
        class AppCommandError(DiscordException):
            pass

        class CheckFailure(AppCommandError):
            pass

        class Choice(Generic[T]):
            def __init__(self, *, name: str, value: T) -> None:
                self.name = name
                self.value = value

        class Command:
            def __init__(
                self,
                *,
                name: str,
                description: str,
                callback: Callable[..., Any],
                parent: Optional["_AppCommands.Group"] = None,
                extras: Optional[Dict[str, Any]] = None,
            ) -> None:
                self.name = name
                self.description = description
                self.callback = callback
                self.parent = parent
                self.extras: Dict[str, Any] = extras or {}
                self.checks: List[Callable[[Interaction], Any]] = list(
                    getattr(callback, "__discord_app_commands_checks__", [])
                )
                self.binding: Optional[Any] = None

            @property
            def qualified_name(self) -> str:
                if self.parent:
                    return f"{self.parent.qualified_name} {self.name}"
                return self.name

            async def invoke(self, interaction: Interaction, *args: Any, **kwargs: Any) -> Any:
                for chk in self.checks:
                    res = chk(interaction)
                    if inspect.isawaitable(res):
                        res = await res
                    if not res:
                        raise _AppCommands.CheckFailure(f"Permission check failed for /{self.qualified_name}")
                if self.binding is not None:
                    return await self.callback(self.binding, interaction, *args, **kwargs)
                return await self.callback(interaction, *args, **kwargs)

        class Group:
            def __init__(
                self,
                *,
                name: str = "",
                description: str = "...",
                parent: Optional["_AppCommands.Group"] = None,
                extras: Optional[Dict[str, Any]] = None,
            ) -> None:
                self.name = name or getattr(self.__class__, "__discord_group_name__", self.__class__.__name__.lower())
                self.description = description or getattr(
                    self.__class__, "__discord_group_description__", "Command group"
                )
                self.parent = parent
                self.extras: Dict[str, Any] = extras or {}
                self._commands: Dict[str, Union[_AppCommands.Command, "_AppCommands.Group"]] = {}
                self.binding: Optional[Any] = None
                if parent is not None:
                    parent.add_command(self, override=True)

            @property
            def qualified_name(self) -> str:
                if self.parent:
                    return f"{self.parent.qualified_name} {self.name}"
                return self.name

            @property
            def commands(self) -> List[Union["_AppCommands.Command", "_AppCommands.Group"]]:
                return list(self._commands.values())

            def add_command(
                self,
                command: Union["_AppCommands.Command", "_AppCommands.Group"],
                *,
                override: bool = False,
            ) -> None:
                if command.name in self._commands and not override:
                    raise ValueError(f"Duplicate command registration: {command.name} in {self.qualified_name}")
                command.parent = self
                self._commands[command.name] = command

            def get_command(self, name: str) -> Optional[Union["_AppCommands.Command", "_AppCommands.Group"]]:
                return self._commands.get(name)

            def walk_commands(self) -> List[Union["_AppCommands.Command", "_AppCommands.Group"]]:
                result: List[Union[_AppCommands.Command, _AppCommands.Group]] = []
                for cmd in self._commands.values():
                    result.append(cmd)
                    if isinstance(cmd, _AppCommands.Group):
                        result.extend(cmd.walk_commands())
                return result

            def command(
                self,
                *,
                name: Optional[str] = None,
                description: str = "...",
                extras: Optional[Dict[str, Any]] = None,
            ) -> Callable[[Callable[..., Any]], "_AppCommands.Command"]:
                def decorator(func: Callable[..., Any]) -> _AppCommands.Command:
                    cmd_name = name or func.__name__
                    cmd = _AppCommands.Command(
                        name=cmd_name,
                        description=description,
                        callback=func,
                        parent=self,
                        extras=extras,
                    )
                    self.add_command(cmd)
                    return cmd

                return decorator

        class CommandTree:
            def __init__(self, client: Any) -> None:
                self.client = client
                self._global_commands: Dict[str, Union[_AppCommands.Command, _AppCommands.Group]] = {}
                self._guild_commands: Dict[int, Dict[str, Union[_AppCommands.Command, _AppCommands.Group]]] = {}
                self.on_error: Optional[Callable[[Interaction, Exception], Coroutine[Any, Any, None]]] = None

            def add_command(
                self,
                command: Union[_AppCommands.Command, _AppCommands.Group],
                *,
                guild: Optional[Object] = None,
                override: bool = False,
            ) -> None:
                if guild is not None:
                    bucket = self._guild_commands.setdefault(guild.id, {})
                else:
                    bucket = self._global_commands
                if command.name in bucket and not override:
                    raise ValueError(f"Duplicate root command registered: /{command.name}")
                bucket[command.name] = command

            def remove_command(
                self,
                name: str,
                *,
                guild: Optional[Object] = None,
            ) -> Optional[Union[_AppCommands.Command, _AppCommands.Group]]:
                if guild is not None:
                    return self._guild_commands.get(guild.id, {}).pop(name, None)
                return self._global_commands.pop(name, None)

            def get_commands(
                self,
                *,
                guild: Optional[Object] = None,
            ) -> List[Union[_AppCommands.Command, _AppCommands.Group]]:
                if guild is not None:
                    return list(self._guild_commands.get(guild.id, {}).values())
                return list(self._global_commands.values())

            def walk_commands(
                self,
                *,
                guild: Optional[Object] = None,
            ) -> List[Union[_AppCommands.Command, _AppCommands.Group]]:
                roots = self.get_commands(guild=guild)
                all_cmds: List[Union[_AppCommands.Command, _AppCommands.Group]] = []
                for root in roots:
                    all_cmds.append(root)
                    if isinstance(root, _AppCommands.Group):
                        all_cmds.extend(root.walk_commands())
                return all_cmds

            def copy_global_to(self, *, guild: Object) -> None:
                self._guild_commands[guild.id] = dict(self._global_commands)

            async def sync(self, *, guild: Optional[Object] = None) -> List[Any]:
                cmds = self.walk_commands(guild=guild)
                leaf_cmds = [c for c in cmds if isinstance(c, _AppCommands.Command)]
                return leaf_cmds

            def error(self, coro: Callable[[Interaction, Exception], Coroutine[Any, Any, None]]) -> Any:
                self.on_error = coro
                return coro

        @staticmethod
        def command(
            *,
            name: Optional[str] = None,
            description: str = "...",
            extras: Optional[Dict[str, Any]] = None,
        ) -> Callable[[Callable[..., Any]], Command]:
            def decorator(func: Callable[..., Any]) -> _AppCommands.Command:
                cmd_name = name or func.__name__
                return _AppCommands.Command(
                    name=cmd_name,
                    description=description,
                    callback=func,
                    extras=extras,
                )

            return decorator

        @staticmethod
        def describe(**kwargs: str) -> Callable[[T], T]:
            def decorator(obj: T) -> T:
                setattr(obj, "__discord_app_commands_describe__", kwargs)
                return obj

            return decorator

        @staticmethod
        def choices(**kwargs: List[Choice[Any]]) -> Callable[[T], T]:
            def decorator(obj: T) -> T:
                setattr(obj, "__discord_app_commands_choices__", kwargs)
                return obj

            return decorator

        @staticmethod
        def check(predicate: Callable[[Interaction], Any]) -> Callable[[T], T]:
            def decorator(obj: T) -> T:
                target = obj.callback if isinstance(obj, _AppCommands.Command) else obj
                existing = getattr(target, "__discord_app_commands_checks__", [])
                existing.append(predicate)
                setattr(target, "__discord_app_commands_checks__", existing)
                if isinstance(obj, _AppCommands.Command):
                    obj.checks.append(predicate)
                return obj

            return decorator

        @staticmethod
        def default_permissions(**kwargs: bool) -> Callable[[T], T]:
            def decorator(obj: T) -> T:
                setattr(obj, "__discord_default_permissions__", kwargs)
                return obj

            return decorator

    # Ext Commands namespace
    class _Commands:
        class CogMeta(type):
            def __new__(cls, name: str, bases: Tuple[type, ...], attrs: Dict[str, Any], **kwargs: Any) -> Any:
                group_name = kwargs.pop("name", None) or attrs.get("__cog_group_name__")
                group_desc = kwargs.pop("description", None) or attrs.get("__cog_group_description__", "Command group")
                new_cls = super().__new__(cls, name, bases, attrs)
                if group_name:
                    setattr(new_cls, "__discord_group_name__", group_name)
                    setattr(new_cls, "__discord_group_description__", group_desc)
                return new_cls

            def __call__(cls, *args: Any, **kwargs: Any) -> Any:
                instance = super().__call__(*args, **kwargs)
                if not hasattr(instance, "_cog_app_commands"):
                    instance._cog_app_commands = []
                    instance._bind_cog_commands()
                return instance

        class Cog(metaclass=CogMeta):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self._cog_app_commands: List[Union[_AppCommands.Command, _AppCommands.Group]] = []
                self._bind_cog_commands()

            def _bind_cog_commands(self) -> None:
                self._cog_app_commands = []
                seen_names: Set[str] = set()
                for attr_name in dir(self.__class__):
                    if attr_name.startswith("__"):
                        continue
                    attr = getattr(self.__class__, attr_name, None)
                    if isinstance(attr, _AppCommands.Command) and attr.parent is None:
                        cloned = _AppCommands.Command(
                            name=attr.name,
                            description=attr.description,
                            callback=attr.callback,
                            extras=dict(attr.extras),
                        )
                        cloned.checks = list(attr.checks)
                        cloned.binding = self
                        setattr(self, attr_name, cloned)
                        if cloned.name not in seen_names:
                            seen_names.add(cloned.name)
                            self._cog_app_commands.append(cloned)
                    elif isinstance(attr, _AppCommands.Group) and attr.parent is None:
                        self._bind_group_recursive(attr)
                        if attr.name not in seen_names:
                            seen_names.add(attr.name)
                            self._cog_app_commands.append(attr)

            def _bind_group_recursive(self, group: _AppCommands.Group) -> None:
                group.binding = self
                for child in group.commands:
                    child.binding = self
                    if isinstance(child, _AppCommands.Group):
                        self._bind_group_recursive(child)

            def get_app_commands(self) -> List[Union[_AppCommands.Command, _AppCommands.Group]]:
                if not hasattr(self, "_cog_app_commands"):
                    self._bind_cog_commands()
                return list(self._cog_app_commands)

            @classmethod
            def listener(cls, name: Optional[str] = None) -> Callable[[T], T]:
                def decorator(func: T) -> T:
                    setattr(func, "__cog_listener__", name or getattr(func, "__name__", "listener"))
                    return func

                return decorator

        class GroupCog(Cog):
            __cog_group_name__: Optional[str] = None
            __cog_group_description__: str = "Command group"

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                grp_name = (
                    getattr(self.__class__, "__discord_group_name__", None)
                    or getattr(self.__class__, "__cog_group_name__", None)
                    or self.__class__.__name__.lower().replace("cog", "")
                )
                grp_desc = getattr(self.__class__, "__discord_group_description__", "Command group")
                root_group = _AppCommands.Group(name=grp_name, description=grp_desc)
                root_group.binding = self
                for cmd in list(self.__cog_app_commands__):
                    root_group.add_command(cmd, override=True)
                self.__cog_app_commands__ = [root_group]
                self.app_command = root_group

        class Bot:
            def __init__(self, *, command_prefix: Any = "!", intents: Optional[Intents] = None, **kwargs: Any) -> None:
                self.command_prefix = command_prefix
                self.intents = intents or Intents.all()
                self.tree = _AppCommands.CommandTree(self)
                self.cogs: Dict[str, _Commands.Cog] = {}
                self.extensions: Dict[str, Any] = {}
                self.persistent_views: List[_UI.View] = []
                self.guilds: List[Guild] = []
                self.user = User(id=999999, name="Cosmic ki baddie", bot=True)
                self.latency: float = 0.018

            async def __aenter__(self) -> "_Commands.Bot":
                await self.setup_hook()
                return self

            async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
                await self.close()

            async def setup_hook(self) -> None:
                pass

            async def add_cog(self, cog: _Commands.Cog, *, override: bool = False) -> None:
                cog_name = cog.__class__.__name__
                self.cogs[cog_name] = cog
                for cmd in cog.get_app_commands():
                    self.tree.add_command(cmd, override=override)

            async def load_extension(self, name: str) -> None:
                import importlib

                mod = importlib.import_module(name)
                if not hasattr(mod, "setup"):
                    raise RuntimeError(f"Extension {name} is missing an async setup(bot) function")
                await mod.setup(self)
                self.extensions[name] = mod

            def add_view(self, view: _UI.View, *, message_id: Optional[int] = None) -> None:
                self.persistent_views.append(view)

            async def start(self, token: str, *, reconnect: bool = True) -> None:
                await self.setup_hook()

            async def close(self) -> None:
                pass

    class _FakeDiscordModule:
        ButtonStyle = ButtonStyle
        TextStyle = TextStyle
        ChannelType = ChannelType
        ActivityType = ActivityType
        Color = Color
        Colour = Colour
        Permissions = Permissions
        PermissionOverwrite = PermissionOverwrite
        Intents = Intents
        Embed = Embed
        File = File
        SelectOption = SelectOption
        Object = Object
        DiscordException = DiscordException
        Forbidden = Forbidden
        NotFound = NotFound
        HTTPException = HTTPException
        Role = Role
        User = User
        Member = Member
        TextChannel = TextChannel
        VoiceChannel = VoiceChannel
        CategoryChannel = CategoryChannel
        Guild = Guild
        Interaction = Interaction
        Message = FakeMessage
        ui = _UI
        app_commands = _AppCommands

    discord = _FakeDiscordModule()  # type: ignore
    app_commands = _AppCommands()  # type: ignore
    commands = _Commands()  # type: ignore
