import os
import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("reaction_bot.voice")

REQUIRED_MUSIC_ROLE_ID = int(os.getenv("MUSIC_ROLE_ID", "1529365517247320114"))

def user_has_music_role(user: discord.User | discord.Member) -> bool:
    """Checks if a user has the specific voice/music role (ID: 1529365517247320114)."""
    if isinstance(user, discord.Member):
        return any(role.id == REQUIRED_MUSIC_ROLE_ID for role in user.roles)
    return False

# Alias for clarity
user_has_voice_role = user_has_music_role

async def check_music_role(interaction: discord.Interaction) -> bool:
    """Check helper that enforces role requirement and sends feedback if user lacks it."""
    if not user_has_music_role(interaction.user):
        await interaction.response.send_message(
            f"❌ You must have the role with ID `{REQUIRED_MUSIC_ROLE_ID}` to use voice commands.",
            ephemeral=True
        )
        return False
    return True

check_voice_role = check_music_role


async def connect_or_move_to_channel(
    guild: discord.Guild,
    channel: discord.VoiceChannel | discord.StageChannel
) -> discord.VoiceClient:
    """Connects to a voice channel or moves to it if already connected."""
    vc = guild.voice_client
    if vc and vc.is_connected():
        if vc.channel.id != channel.id:
            await vc.move_to(channel)
        return vc
    return await channel.connect()


def setup_music_commands(bot: commands.Bot):
    """Registers voice commands (/join, /leave) to the bot tree."""

    @bot.tree.command(name="join", description="Make the bot join a specific voice channel or your current channel.")
    @app_commands.describe(channel="Voice channel for the bot to join (optional, defaults to your current channel)")
    async def join_cmd(interaction: discord.Interaction, channel: discord.VoiceChannel | discord.StageChannel | None = None):
        if not await check_music_role(interaction):
            return

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Voice commands can only be used in a server.", ephemeral=True)
            return

        target_channel = channel
        if not target_channel:
            voice_state = interaction.user.voice
            if voice_state and voice_state.channel:
                target_channel = voice_state.channel

        if not target_channel:
            await interaction.response.send_message("❌ You must be in a voice channel or specify one to join.", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            await connect_or_move_to_channel(interaction.guild, target_channel)
        except Exception as e:
            logger.error(f"Failed to join voice channel {target_channel.id}: {e}", exc_info=e)
            await interaction.followup.send(f"❌ Failed to join voice channel: {e}")
            return

        await interaction.followup.send(f"🔊 Joined {target_channel.mention}!")

    @bot.tree.command(name="leave", description="Make the bot leave the voice channel.")
    async def leave_cmd(interaction: discord.Interaction):
        if not await check_music_role(interaction):
            return

        if not interaction.guild:
            await interaction.response.send_message("❌ Voice commands can only be used in a server.", ephemeral=True)
            return

        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            await interaction.response.send_message("ℹ️ The bot is not currently connected to any voice channel.", ephemeral=True)
            return

        channel_name = vc.channel.name if vc.channel else "the voice channel"
        await vc.disconnect()
        await interaction.response.send_message(f"👋 Left **{channel_name}**.")

# Alias for setup function
setup_voice_commands = setup_music_commands
