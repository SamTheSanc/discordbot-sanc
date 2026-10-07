import asyncio
import logging
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

logger = logging.getLogger("reaction_bot.music")

REQUIRED_MUSIC_ROLE_ID = 1529365517247320114

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

def user_has_music_role(user: discord.User | discord.Member) -> bool:
    """Checks if a user has the specific music role (ID: 1529365517247320114)."""
    if isinstance(user, discord.Member):
        return any(role.id == REQUIRED_MUSIC_ROLE_ID for role in user.roles)
    return False

async def check_music_role(interaction: discord.Interaction) -> bool:
    """Check helper that enforces role requirement and sends feedback if user lacks it."""
    if not user_has_music_role(interaction.user):
        await interaction.response.send_message(
            f"❌ You must have the role with ID `{REQUIRED_MUSIC_ROLE_ID}` to use music commands.",
            ephemeral=True
        )
        return False
    return True

def format_duration(seconds: int | float | None) -> str:
    """Format duration in seconds to HH:MM:SS or MM:SS format."""
    if not seconds:
        return "Live / Unknown"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

async def fetch_song_info(query: str, requester: discord.Member) -> dict | None:
    """Extract YouTube song metadata asynchronously using yt-dlp."""
    loop = asyncio.get_running_loop()
    try:
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
    except Exception as e:
        logger.error(f"yt-dlp extraction error for query '{query}': {e}")
        return None

    if not data:
        return None

    if 'entries' in data:
        if not data['entries']:
            return None
        data = data['entries'][0]

    return {
        'stream_url': data.get('url'),
        'webpage_url': data.get('webpage_url') or data.get('url'),
        'title': data.get('title', 'Unknown Title'),
        'duration': data.get('duration', 0),
        'thumbnail': data.get('thumbnail'),
        'uploader': data.get('uploader', 'Unknown Channel'),
        'requester': requester
    }


class GuildMusicManager:
    """Manages audio queue, playback state, volume, and AFK mode for a guild."""

    def __init__(self, guild_id: int, bot: commands.Bot):
        self.guild_id = guild_id
        self.bot = bot
        self.queue: list[dict] = []
        self.current: dict | None = None
        self.volume: float = 0.70  # Default volume: 70%
        self.is_afk: bool = False
        self.text_channel: discord.TextChannel | None = None

    @property
    def voice_client(self) -> discord.VoiceClient | None:
        guild = self.bot.get_guild(self.guild_id)
        return guild.voice_client if guild else None

    async def join_channel(self, channel: discord.VoiceChannel | discord.StageChannel) -> discord.VoiceClient:
        vc = self.voice_client
        if vc and vc.is_connected():
            if vc.channel.id != channel.id:
                await vc.move_to(channel)
            return vc
        else:
            return await channel.connect()

    def set_volume(self, level: int):
        self.volume = max(0, min(100, level)) / 100.0
        vc = self.voice_client
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = self.volume

    def stop_and_clear(self):
        self.queue.clear()
        self.current = None
        vc = self.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()

    def play_next(self, error=None):
        if error:
            logger.error(f"Playback error in guild {self.guild_id}: {error}")
        
        future = asyncio.run_coroutine_threadsafe(self._process_queue(), self.bot.loop)
        try:
            future.result()
        except Exception as e:
            logger.error(f"Error in play_next callback: {e}")

    async def _process_queue(self):
        vc = self.voice_client
        if not vc or not vc.is_connected():
            return

        if self.is_afk:
            self.current = None
            return

        if self.queue:
            self.current = self.queue.pop(0)
            stream_url = self.current['stream_url']

            try:
                audio_source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
                volume_source = discord.PCMVolumeTransformer(audio_source, volume=self.volume)
                vc.play(volume_source, after=self.play_next)

                if self.text_channel:
                    embed = discord.Embed(
                        title="🎶 Now Playing",
                        description=f"[{self.current['title']}]({self.current['webpage_url']})",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Duration", value=format_duration(self.current['duration']), inline=True)
                    embed.add_field(name="Requested By", value=self.current['requester'].mention, inline=True)
                    embed.add_field(name="Volume", value=f"{int(self.volume * 100)}%", inline=True)
                    if self.current.get('thumbnail'):
                        embed.set_thumbnail(url=self.current['thumbnail'])
                    await self.text_channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Error starting audio stream: {e}")
                if self.text_channel:
                    await self.text_channel.send(f"❌ Error playing track: `{e}`")
                await self._process_queue()
        else:
            self.current = None


_guild_managers: dict[int, GuildMusicManager] = {}

def get_music_manager(guild_id: int, bot: commands.Bot) -> GuildMusicManager:
    if guild_id not in _guild_managers:
        _guild_managers[guild_id] = GuildMusicManager(guild_id, bot)
    return _guild_managers[guild_id]


def setup_music_commands(bot: commands.Bot):
    """Registers music and AFK slash commands to the bot tree."""

    @bot.tree.command(name="join", description="Make the bot join a specific voice channel or your current channel.")
    @app_commands.describe(channel="Voice channel for the bot to join (optional, defaults to your current channel)")
    async def join_cmd(interaction: discord.Interaction, channel: discord.VoiceChannel | discord.StageChannel | None = None):
        if not await check_music_role(interaction):
            return

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Music commands can only be used in a server.", ephemeral=True)
            return

        manager = get_music_manager(interaction.guild.id, bot)
        target_channel = channel
        if not target_channel:
            voice_state = interaction.user.voice
            if voice_state and voice_state.channel:
                target_channel = voice_state.channel

        if not target_channel:
            await interaction.response.send_message("❌ You must be in a voice channel or specify one to join.", ephemeral=True)
            return

        await interaction.response.defer()
        manager.text_channel = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None

        try:
            await manager.join_channel(target_channel)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to join voice channel: {e}")
            return

        await interaction.followup.send(f"🔊 Joined {target_channel.mention}!")


    @bot.tree.command(name="play", description="Play YouTube music or add a song to the queue.")
    @app_commands.describe(
        query="YouTube video URL or search keywords",
        channel="Voice channel to join (optional, defaults to your current channel)"
    )
    async def play(interaction: discord.Interaction, query: str, channel: discord.VoiceChannel | discord.StageChannel | None = None):
        if not await check_music_role(interaction):
            return

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Music commands can only be used in a server.", ephemeral=True)
            return

        manager = get_music_manager(interaction.guild.id, bot)
        target_channel = channel
        if not target_channel:
            voice_state = interaction.user.voice
            if voice_state and voice_state.channel:
                target_channel = voice_state.channel
            elif manager.voice_client and manager.voice_client.is_connected():
                target_channel = manager.voice_client.channel

        if not target_channel:
            await interaction.response.send_message("❌ You must be connected to a voice channel or specify one to use `/play`.", ephemeral=True)
            return

        await interaction.response.defer()
        manager.text_channel = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None

        try:
            await manager.join_channel(target_channel)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to join voice channel: {e}")
            return

        # Disable AFK mode when user plays music
        manager.is_afk = False

        song = await fetch_song_info(query, interaction.user)
        if not song or not song.get('stream_url'):
            await interaction.followup.send("❌ Could not find or load YouTube track. Please check your query or link.")
            return

        vc = manager.voice_client
        is_playing = vc and (vc.is_playing() or vc.is_paused())

        manager.queue.append(song)

        if not is_playing:
            await manager._process_queue()
            embed = discord.Embed(
                title="🎵 Track Loaded",
                description=f"Starting playback for [{song['title']}]({song['webpage_url']})",
                color=discord.Color.blue()
            )
        else:
            position = len(manager.queue)
            embed = discord.Embed(
                title="📝 Added to Queue",
                description=f"[{song['title']}]({song['webpage_url']})",
                color=discord.Color.gold()
            )
            embed.add_field(name="Position in Queue", value=f"#{position}", inline=True)
            embed.add_field(name="Duration", value=format_duration(song['duration']), inline=True)
            embed.add_field(name="Requested By", value=interaction.user.mention, inline=True)

        if song.get('thumbnail'):
            embed.set_thumbnail(url=song['thumbnail'])

        await interaction.followup.send(embed=embed)


    @bot.tree.command(name="queue", description="Check current music queue, status, and volume.")
    async def queue_cmd(interaction: discord.Interaction):
        if not await check_music_role(interaction):
            return

        if not interaction.guild:
            await interaction.response.send_message("❌ Music commands can only be used in a server.", ephemeral=True)
            return

        manager = get_music_manager(interaction.guild.id, bot)
        current_vol = int(manager.volume * 100)

        embed = discord.Embed(
            title=f"🎶 Music Queue — {interaction.guild.name}",
            color=discord.Color.purple()
        )

        status_str = "💤 AFK (Staying in VC)" if manager.is_afk else ("▶️ Playing" if manager.current else "⏹️ Idle")
        embed.add_field(name="Status", value=status_str, inline=True)
        embed.add_field(name="Volume", value=f"🔊 {current_vol}%", inline=True)

        if manager.current:
            cur = manager.current
            embed.add_field(
                name="🎧 Currently Playing",
                value=f"[{cur['title']}]({cur['webpage_url']}) | `{format_duration(cur['duration'])}` | Requested by {cur['requester'].mention}",
                inline=False
            )

        if manager.queue:
            queue_lines = []
            for idx, song in enumerate(manager.queue[:10], start=1):
                queue_lines.append(
                    f"`{idx}.` [{song['title']}]({song['webpage_url']}) | `{format_duration(song['duration'])}` | {song['requester'].mention}"
                )
            if len(manager.queue) > 10:
                queue_lines.append(f"\n*...and {len(manager.queue) - 10} more song(s) in queue*")

            embed.add_field(name="📜 Queue List", value="\n".join(queue_lines), inline=False)
        else:
            embed.add_field(name="📜 Queue List", value="*Queue is currently empty.*", inline=False)

        await interaction.response.send_message(embed=embed)


    @bot.tree.command(name="volume", description="Change playback volume level (0-100, default is 70).")
    @app_commands.describe(level="Volume percentage from 0 to 100")
    async def volume_cmd(interaction: discord.Interaction, level: int):
        if not await check_music_role(interaction):
            return

        if not interaction.guild:
            await interaction.response.send_message("❌ Music commands can only be used in a server.", ephemeral=True)
            return

        if level < 0 or level > 100:
            await interaction.response.send_message("❌ Volume level must be between 0 and 100.", ephemeral=True)
            return

        manager = get_music_manager(interaction.guild.id, bot)
        manager.set_volume(level)

        await interaction.response.send_message(f"🔊 Volume set to **{level}%** (Default is 70%).")


    @bot.tree.command(name="afk", description="Bot stays in the voice channel without playing music.")
    @app_commands.describe(channel="Voice channel for the bot to join (optional, defaults to your current channel)")
    async def afk_cmd(interaction: discord.Interaction, channel: discord.VoiceChannel | discord.StageChannel | None = None):
        if not await check_music_role(interaction):
            return

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Music commands can only be used in a server.", ephemeral=True)
            return

        manager = get_music_manager(interaction.guild.id, bot)
        target_channel = channel
        if not target_channel:
            voice_state = interaction.user.voice
            if voice_state and voice_state.channel:
                target_channel = voice_state.channel
            elif manager.voice_client and manager.voice_client.is_connected():
                target_channel = manager.voice_client.channel

        if not target_channel:
            await interaction.response.send_message("❌ You must be in a voice channel or specify one for the bot to join in AFK mode.", ephemeral=True)
            return

        await interaction.response.defer()
        manager.text_channel = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None

        try:
            vc = await manager.join_channel(target_channel)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to join voice channel: {e}")
            return

        manager.is_afk = True
        manager.stop_and_clear()

        embed = discord.Embed(
            title="💤 Bot in AFK Mode",
            description=f"Bot joined and is now staying in {target_channel.mention} with no music playing.",
            color=discord.Color.dark_grey()
        )
        embed.set_footer(text="Use /play to play music or /stop to make the bot leave.")
        await interaction.followup.send(embed=embed)


    @bot.tree.command(name="skip", description="Skip the currently playing song.")
    async def skip_cmd(interaction: discord.Interaction):
        if not await check_music_role(interaction):
            return

        if not interaction.guild:
            await interaction.response.send_message("❌ Music commands can only be used in a server.", ephemeral=True)
            return

        manager = get_music_manager(interaction.guild.id, bot)
        vc = manager.voice_client

        if not vc or not (vc.is_playing() or vc.is_paused()):
            await interaction.response.send_message("ℹ️ No music is currently playing.", ephemeral=True)
            return

        vc.stop()
        await interaction.response.send_message("⏭️ Skipped current track.")


    @bot.tree.command(name="stop", description="Stop music, clear queue, and leave voice channel.")
    async def stop_cmd(interaction: discord.Interaction):
        if not await check_music_role(interaction):
            return

        if not interaction.guild:
            await interaction.response.send_message("❌ Music commands can only be used in a server.", ephemeral=True)
            return

        manager = get_music_manager(interaction.guild.id, bot)
        manager.stop_and_clear()
        manager.is_afk = False

        vc = manager.voice_client
        if vc and vc.is_connected():
            await vc.disconnect()

        await interaction.response.send_message("⏹️ Stopped playback, cleared queue, and left the voice channel.")


    @bot.tree.command(name="pause", description="Pause current music playback.")
    async def pause_cmd(interaction: discord.Interaction):
        if not await check_music_role(interaction):
            return

        if not interaction.guild:
            await interaction.response.send_message("❌ Music commands can only be used in a server.", ephemeral=True)
            return

        manager = get_music_manager(interaction.guild.id, bot)
        vc = manager.voice_client

        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Music playback paused.")
        else:
            await interaction.response.send_message("ℹ️ No music is currently playing to pause.", ephemeral=True)


    @bot.tree.command(name="resume", description="Resume paused music playback.")
    async def resume_cmd(interaction: discord.Interaction):
        if not await check_music_role(interaction):
            return

        if not interaction.guild:
            await interaction.response.send_message("❌ Music commands can only be used in a server.", ephemeral=True)
            return

        manager = get_music_manager(interaction.guild.id, bot)
        vc = manager.voice_client

        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Music playback resumed.")
        else:
            await interaction.response.send_message("ℹ️ Music is not currently paused.", ephemeral=True)
