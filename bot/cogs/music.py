"""
Music System Cog for Cosmic ki baddie.

Implements all 13 required music commands plus `/musicdiagnostics`:
- `/play`
- `/pause`
- `/resume`
- `/skip`
- `/stop`
- `/queue`
- `/nowplaying`
- `/volume`
- `/loop`
- `/shuffle`
- `/remove`
- `/clearqueue`
- `/disconnect`
- `/musicdiagnostics` (Music system diagnostics & FFmpeg/PyNaCl verification)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot.core.discord_compat import app_commands, commands, discord
from bot.database.models import PermissionLevel
from bot.utils.checks import require_permission_level
from bot.utils.formatting import format_duration

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot


class InteractivePlayerView(discord.ui.View):
    """Interactive Music Player Controls attached to `/play` and `/nowplaying`."""

    def __init__(self, bot: "CosmicBot", guild_id: int) -> None:
        super().__init__(timeout=300.0)
        self.bot = bot
        self.guild_id = int(guild_id)

        pause_btn = discord.ui.Button(label="Pause / Resume", style=discord.ButtonStyle.primary, custom_id="cosmic:music:toggle")
        skip_btn = discord.ui.Button(label="Skip", style=discord.ButtonStyle.secondary, custom_id="cosmic:music:skip")
        loop_btn = discord.ui.Button(label="Cycle Loop", style=discord.ButtonStyle.secondary, custom_id="cosmic:music:loop")
        stop_btn = discord.ui.Button(label="Stop", style=discord.ButtonStyle.danger, custom_id="cosmic:music:stop")

        pause_btn.callback = self._on_toggle
        skip_btn.callback = self._on_skip
        loop_btn.callback = self._on_loop
        stop_btn.callback = self._on_stop

        self.add_item(pause_btn)
        self.add_item(skip_btn)
        self.add_item(loop_btn)
        self.add_item(stop_btn)

    async def _on_toggle(self, interaction: discord.Interaction) -> None:
        state = self.bot.music_service.get_state(self.guild_id)
        if state.is_paused:
            _, msg = await self.bot.music_service.resume(self.guild_id)
        else:
            _, msg = await self.bot.music_service.pause(self.guild_id)
        await interaction.response.send_message(msg, ephemeral=True)

    async def _on_skip(self, interaction: discord.Interaction) -> None:
        _, msg, _ = await self.bot.music_service.skip(self.guild_id)
        await interaction.response.send_message(msg, ephemeral=True)

    async def _on_loop(self, interaction: discord.Interaction) -> None:
        state = self.bot.music_service.get_state(self.guild_id)
        order = ["off", "track", "queue"]
        next_mode = order[(order.index(state.loop_mode) + 1) % len(order)]
        _, msg = await self.bot.music_service.set_loop_mode(self.guild_id, next_mode)
        await interaction.response.send_message(msg, ephemeral=True)

    async def _on_stop(self, interaction: discord.Interaction) -> None:
        _, msg = await self.bot.music_service.stop_and_disconnect(self.guild_id)
        await interaction.response.send_message(msg, ephemeral=True)


class MusicCog(commands.Cog):
    """Full-featured asynchronous Music Player, Queue Manager, and Diagnostics."""

    def __init__(self, bot: "CosmicBot") -> None:
        self.bot = bot

    @app_commands.command(name="play", description="Validate and play a song or stream URL in your voice channel.")
    @app_commands.describe(query="Song search query or direct audio URL (.mp3/.ogg/stream)")
    async def play_command(self, interaction: discord.Interaction, query: str) -> None:
        if interaction.guild is None:
            return
        voice_state = getattr(interaction.user, "voice", None)
        voice_ch = getattr(voice_state, "channel", None) if voice_state else None
        vc_id = int(voice_ch.id) if voice_ch else None

        ok, msg, track = await self.bot.music_service.enqueue_track(
            guild_id=int(interaction.guild.id),
            query=query,
            requester_id=int(interaction.user.id),
            requester_name=interaction.user.name,
            voice_channel_id=vc_id,
        )
        if not ok or track is None:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        embed = discord.Embed(
            title="Cosmic ki baddie Music Player",
            description=msg,
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Track", value=f"[{track.title}]({track.url})", inline=True)
        embed.add_field(name="Duration", value=format_duration(track.duration_seconds), inline=True)
        embed.add_field(name="Requested By", value=f"<@{track.requester_id}>", inline=True)
        view = InteractivePlayerView(self.bot, int(interaction.guild.id))
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="pause", description="Pause the currently playing track.")
    @require_permission_level(PermissionLevel.DJ, module_name="music")
    async def pause_command(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        ok, msg = await self.bot.music_service.pause(int(interaction.guild.id))
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="resume", description="Resume a paused track.")
    @require_permission_level(PermissionLevel.DJ, module_name="music")
    async def resume_command(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        ok, msg = await self.bot.music_service.resume(int(interaction.guild.id))
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="skip", description="Skip the current track or cast a skip vote.")
    async def skip_command(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        ok, msg, _ = await self.bot.music_service.skip(int(interaction.guild.id))
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="stop", description="Stop playback and clear the active music queue.")
    @require_permission_level(PermissionLevel.DJ, module_name="music")
    async def stop_command(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        ok, msg = await self.bot.music_service.stop_and_disconnect(int(interaction.guild.id))
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="queue", description="Display the current music queue and loop/volume settings.")
    async def queue_command(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        state = self.bot.music_service.get_state(int(interaction.guild.id))
        embed = discord.Embed(
            title=f"Music Queue — {interaction.guild.name}",
            color=discord.Color.blurple(),
        )
        if state.current_track:
            embed.add_field(
                name="Now Playing",
                value=f"**{state.current_track.title}** ({format_duration(state.current_track.duration_seconds)}) — Requested by <@{state.current_track.requester_id}>",
                inline=False,
            )
        else:
            embed.add_field(name="Now Playing", value="Nothing is currently playing.", inline=False)

        if state.queue:
            q_lines = [
                f"`#{idx + 1}` **{t.title}** ({format_duration(t.duration_seconds)}) · <@{t.requester_id}>"
                for idx, t in enumerate(state.queue[:15])
            ]
            embed.add_field(name=f"Up Next ({len(state.queue)} Tracks)", value="\n".join(q_lines), inline=False)
        else:
            embed.add_field(name="Up Next", value="Queue is empty.", inline=False)

        embed.set_footer(text=f"Volume: {state.volume}% · Loop Mode: {state.loop_mode}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="nowplaying", description="Display detailed information and controls for the current track.")
    async def nowplaying_command(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        state = self.bot.music_service.get_state(int(interaction.guild.id))
        if not state.current_track:
            await interaction.response.send_message("No track is currently playing.", ephemeral=True)
            return
        t = state.current_track
        embed = discord.Embed(
            title=f"Now Playing: {t.title}",
            description=f"Source URL: {t.url}",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Duration", value=format_duration(t.duration_seconds), inline=True)
        embed.add_field(name="Volume", value=f"{state.volume}%", inline=True)
        embed.add_field(name="Loop Mode", value=state.loop_mode, inline=True)
        await interaction.response.send_message(
            embed=embed,
            view=InteractivePlayerView(self.bot, int(interaction.guild.id)),
        )

    @app_commands.command(name="volume", description="Set the music playback volume (0-200%).")
    @app_commands.describe(level="Volume percentage between 0 and 200")
    @require_permission_level(PermissionLevel.DJ, module_name="music")
    async def volume_command(self, interaction: discord.Interaction, level: int) -> None:
        if interaction.guild is None:
            return
        ok, msg = await self.bot.music_service.set_volume(int(interaction.guild.id), int(level))
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="loop", description="Set loop mode: off, track (current song), or queue (entire queue).")
    @app_commands.describe(mode="Loop mode: off, track, or queue")
    @require_permission_level(PermissionLevel.DJ, module_name="music")
    async def loop_command(self, interaction: discord.Interaction, mode: str) -> None:
        if interaction.guild is None:
            return
        ok, msg = await self.bot.music_service.set_loop_mode(int(interaction.guild.id), mode)
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="shuffle", description="Shuffle the tracks in the music queue.")
    @require_permission_level(PermissionLevel.DJ, module_name="music")
    async def shuffle_command(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        ok, msg = await self.bot.music_service.shuffle_queue(int(interaction.guild.id))
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="remove", description="Remove a track at a specific position in the queue.")
    @app_commands.describe(position="1-based position in the queue to remove")
    @require_permission_level(PermissionLevel.DJ, module_name="music")
    async def remove_command(self, interaction: discord.Interaction, position: int) -> None:
        if interaction.guild is None:
            return
        ok, msg = await self.bot.music_service.remove_from_queue(int(interaction.guild.id), int(position))
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="clearqueue", description="Remove all upcoming tracks from the music queue.")
    @require_permission_level(PermissionLevel.DJ, module_name="music")
    async def clearqueue_command(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        ok, msg = await self.bot.music_service.clear_queue(int(interaction.guild.id))
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="disconnect", description="Stop playback and disconnect the bot from the voice channel.")
    @require_permission_level(PermissionLevel.DJ, module_name="music")
    async def disconnect_command(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        ok, msg = await self.bot.music_service.stop_and_disconnect(int(interaction.guild.id))
        if getattr(interaction.guild, "voice_client", None) is not None:
            await interaction.guild.voice_client.disconnect(force=True)
        await interaction.response.send_message(msg)

    @app_commands.command(name="musicdiagnostics", description="Check FFmpeg, PyNaCl, yt-dlp, and voice player health.")
    async def music_diagnostics_command(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        diag = self.bot.music_service.get_diagnostics(int(interaction.guild.id))
        embed = discord.Embed(
            title="Music System Diagnostics",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="FFmpeg Binary", value=f"`{diag['ffmpeg_installed']}` (`{diag['ffmpeg_path']}`)", inline=True)
        embed.add_field(name="PyNaCl Voice", value=f"`{diag['pynacl_installed']}`", inline=True)
        embed.add_field(name="yt-dlp Extractor", value=f"`{diag['yt_dlp_installed']}`", inline=True)
        embed.add_field(name="Active Player", value=str(diag["active_player"]), inline=True)
        embed.add_field(name="Queue Length", value=str(diag["queue_length"]), inline=True)
        embed.add_field(name="Volume / Loop", value=f"{diag['volume']}% / `{diag['loop_mode']}`", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: "CosmicBot") -> None:
    await bot.add_cog(MusicCog(bot))
