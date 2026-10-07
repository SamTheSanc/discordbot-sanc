import os
import logging
import random
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import database 
from emoticons import extract_emoticons
from music import user_has_music_role, setup_music_commands

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("reaction_bot")

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "1238775030444326952"))

def get_env_whitelisted_users() -> set[int]:
    """Parse comma-separated user IDs from the WHITELISTED_USERS environment variable."""
    raw = os.getenv("WHITELISTED_USERS", "")
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True
intents.guilds = True

# Slash commands only - prefix commands disabled
bot = commands.Bot(command_prefix=(), intents=intents, help_command=None)

# Register music slash commands (/play, /queue, /volume, /afk, etc.)
setup_music_commands(bot)

# ----------------- WHITELIST AUTHORIZATION -----------------

async def is_user_authorized(interaction: discord.Interaction) -> bool:
    """Check if the user invoking the slash command is whitelisted or has admin rights."""
    user_id = interaction.user.id

    # 0. Check music role (ID: 1529365517247320114)
    if user_has_music_role(interaction.user):
        return True

    # 1. Check environment variable whitelist
    if user_id in get_env_whitelisted_users():
        return True

    # 2. Check dynamic database whitelist
    if await database.is_whitelisted_db(user_id):
        return True

    # 3. Server administrator
    if interaction.guild and isinstance(interaction.user, discord.Member):
        if interaction.user.guild_permissions.administrator:
            return True

    # 4. Bot application owner
    try:
        if await bot.is_owner(interaction.user):
            return True
    except Exception:
        pass

    return False

def can_manage_whitelist(interaction: discord.Interaction) -> bool:
    """Check if the user is authorized to manage the whitelist."""
    if interaction.user.id in get_env_whitelisted_users():
        return True
    if interaction.guild and isinstance(interaction.user, discord.Member):
        if interaction.user.guild_permissions.administrator:
            return True
    if bot.owner_id and interaction.user.id == bot.owner_id:
        return True
    if bot.owner_ids and interaction.user.id in bot.owner_ids:
        return True
    return False

async def global_whitelist_check(interaction: discord.Interaction) -> bool:
    """Restricts any slash command from executing unless the user is whitelisted."""
    if not await is_user_authorized(interaction):
        cmd_name = interaction.command.name if interaction.command else "unknown"
        logger.info(
            f"Unauthorized command /{cmd_name} attempted by {interaction.user} (ID: {interaction.user.id}) - command not sent."
        )
        return False
    return True

bot.tree.interaction_check = global_whitelist_check

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Handle slash command errors; silently drop unauthorized check failures so nothing sends."""
    if isinstance(error, app_commands.CheckFailure):
        # Silently drop: no message is sent to Discord
        return
    logger.error(f"Error handling slash command: {error}", exc_info=error)

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Emoji and ASCII emoticon counting restricted to channel ID: {TARGET_CHANNEL_ID}")
    await database.init_db()
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")

# ----------------- REACTION EVENTS -----------------

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    # Strictly restrict counting to TARGET_CHANNEL_ID and guilds only
    if not payload.guild_id or payload.channel_id != TARGET_CHANNEL_ID:
        return
    
    try:
        channel = bot.get_channel(payload.channel_id)
        if not channel:
            channel = await bot.fetch_channel(payload.channel_id)
            
        message = await channel.fetch_message(payload.message_id)
        receiver_id = message.author.id
        giver_id = payload.user_id
        emoji_str = str(payload.emoji)

        await database.add_reaction(
            message_id=payload.message_id,
            channel_id=payload.channel_id,
            guild_id=payload.guild_id,
            giver_id=giver_id,
            receiver_id=receiver_id,
            emoji=emoji_str
        )
    except Exception as e:
        logger.error(f"Error handling reaction add: {e}")

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.channel_id != TARGET_CHANNEL_ID:
        return

    try:
        await database.remove_reaction(
            message_id=payload.message_id,
            giver_id=payload.user_id,
            emoji=str(payload.emoji)
        )
    except Exception as e:
        logger.error(f"Error handling reaction remove: {e}")

@bot.event
async def on_raw_reaction_clear(payload: discord.RawReactionClearEvent):
    if payload.channel_id != TARGET_CHANNEL_ID:
        return

    try:
        await database.clear_message_reactions(payload.message_id)
    except Exception as e:
        logger.error(f"Error handling reaction clear: {e}")

@bot.event
async def on_raw_reaction_clear_emoji(payload: discord.RawReactionClearEmojiEvent):
    if payload.channel_id != TARGET_CHANNEL_ID:
        return

    try:
        await database.clear_emoji_reactions(payload.message_id, str(payload.emoji))
    except Exception as e:
        logger.error(f"Error handling reaction clear emoji: {e}")

# ----------------- MESSAGE & EMOTICON EVENTS -----------------

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Count ASCII emoticons only in the allowed channel
    if message.channel.id == TARGET_CHANNEL_ID and message.guild:
        emoticon_counts = extract_emoticons(message.content)
        if emoticon_counts:
            await database.record_emoticons(
                message_id=message.id,
                channel_id=message.channel.id,
                guild_id=message.guild.id,
                user_id=message.author.id,
                emoticons=emoticon_counts
            )

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if after.author.bot or after.channel.id != TARGET_CHANNEL_ID or not after.guild:
        return

    emoticon_counts = extract_emoticons(after.content)
    if emoticon_counts:
        await database.record_emoticons(
            message_id=after.id,
            channel_id=after.channel.id,
            guild_id=after.guild.id,
            user_id=after.author.id,
            emoticons=emoticon_counts
        )
    else:
        await database.delete_message_emoticons(after.id)

@bot.event
async def on_message_delete(message: discord.Message):
    if message.channel.id == TARGET_CHANNEL_ID:
        await database.delete_message_emoticons(message.id)

# ----------------- SLASH COMMANDS -----------------

@bot.tree.command(name="scan", description="Scan past messages in the allowed channel to index reactions and emoticons.")
@app_commands.describe(limit="Number of past messages to scan (default 100)")
@app_commands.default_permissions(administrator=True)
async def scan_channel(interaction: discord.Interaction, limit: int = 100):
    """Scans the allowed channel's past messages for reactions and ASCII emoticons."""
    if not interaction.guild:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return

    await interaction.response.defer()
    
    target_channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not target_channel:
        try:
            target_channel = await bot.fetch_channel(TARGET_CHANNEL_ID)
        except Exception as e:
            await interaction.followup.send(f"❌ Unable to access target channel (`{TARGET_CHANNEL_ID}`): {e}")
            return

    count_messages = 0
    count_reactions = 0
    count_emoticons = 0
    
    async for message in target_channel.history(limit=limit):
        count_messages += 1
        
        # 1. Index message reactions (Emojis)
        receiver_id = message.author.id
        for reaction in message.reactions:
            emoji_str = str(reaction.emoji)
            async for user in reaction.users():
                await database.add_reaction(
                    message_id=message.id,
                    channel_id=target_channel.id,
                    guild_id=interaction.guild.id,
                    giver_id=user.id,
                    receiver_id=receiver_id,
                    emoji=emoji_str
                )
                count_reactions += 1
                
        # 2. Index message text emoticons (ASCII)
        if not message.author.bot:
            emoticons_found = extract_emoticons(message.content)
            if emoticons_found:
                await database.record_emoticons(
                    message_id=message.id,
                    channel_id=target_channel.id,
                    guild_id=interaction.guild.id,
                    user_id=message.author.id,
                    emoticons=emoticons_found
                )
                count_emoticons += sum(emoticons_found.values())

    embed = discord.Embed(
        title="Channel Scan Complete",
        description=(
            f"Scanned **{count_messages}** messages in {target_channel.mention}.\n\n"
            f"• **Indexed Reactions (Emojis):** {count_reactions}\n"
            f"• **Indexed Emoticons (ASCII):** {count_emoticons}"
        ),
        color=discord.Color.green()
    )
    embed.set_footer(text=f"Channel ID: {TARGET_CHANNEL_ID}")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="leaderboard", description="View server top users by reactions and emoticons.")
async def leaderboard(interaction: discord.Interaction):
    """Displays leaderboards for reactions gave/received and emoticons used."""
    if not interaction.guild:
        await interaction.response.send_message("Leaderboards are server-specific and cannot be run in DMs.", ephemeral=True)
        return

    await interaction.response.defer()
    
    top_givers = await database.get_top_givers(guild_id=interaction.guild.id, limit=10)
    top_receivers = await database.get_top_receivers(guild_id=interaction.guild.id, limit=10)
    top_emoticon_users = await database.get_top_emoticon_users(guild_id=interaction.guild.id, limit=10)
    top_emoticons = await database.get_top_emoticons(guild_id=interaction.guild.id, limit=5)
    
    embed = discord.Embed(
        title=f"🏆 Server Leaderboard — {interaction.guild.name}",
        color=discord.Color.gold(),
        description=f"Rankings are strictly tracked from <#{TARGET_CHANNEL_ID}>."
    )
    
    medals = ["🥇", "🥈", "🥉"]
    
    # 1. Format Top Reaction Givers
    givers_text = ""
    if not top_givers:
        givers_text = "No reactions recorded yet."
    else:
        for idx, (user_id, count) in enumerate(top_givers, start=1):
            rank = medals[idx - 1] if idx <= 3 else f"`#{idx}`"
            givers_text += f"{rank} <@{user_id}>: **{count}** gave\n"
            
    # 2. Format Top Reaction Receivers
    receivers_text = ""
    if not top_receivers:
        receivers_text = "No reactions recorded yet."
    else:
        for idx, (user_id, count) in enumerate(top_receivers, start=1):
            rank = medals[idx - 1] if idx <= 3 else f"`#{idx}`"
            receivers_text += f"{rank} <@{user_id}>: **{count}** received\n"

    # 3. Format Top Emoticon Users
    emoticon_users_text = ""
    if not top_emoticon_users:
        emoticon_users_text = "No ASCII emoticons recorded yet."
    else:
        for idx, (user_id, count) in enumerate(top_emoticon_users, start=1):
            rank = medals[idx - 1] if idx <= 3 else f"`#{idx}`"
            emoticon_users_text += f"{rank} <@{user_id}>: **{count}** used\n"
            
    embed.add_field(name="📤 Top Reactions Gave (Emojis)", value=givers_text, inline=False)
    embed.add_field(name="📥 Top Reactions Received (Emojis)", value=receivers_text, inline=False)
    embed.add_field(name="😊 Top Emoticons Used (ASCII)", value=emoticon_users_text, inline=False)

    # 4. Top emoticons summary
    if top_emoticons:
        top_emoticon_str = " | ".join([f"`{emo}`: **{cnt}**" for emo, cnt in top_emoticons])
        embed.add_field(name="✨ Most Popular ASCII Emoticons", value=top_emoticon_str, inline=False)

    embed.set_footer(text=f"Tracked channel ID: {TARGET_CHANNEL_ID}")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="emoticons", description="View ASCII emoticon leaderboard and most used emoticons.")
async def emoticons_leaderboard(interaction: discord.Interaction):
    """Displays dedicated ASCII emoticon leaderboard."""
    if not interaction.guild:
        await interaction.response.send_message("Leaderboards are server-specific and cannot be run in DMs.", ephemeral=True)
        return

    await interaction.response.defer()
    top_emoticon_users = await database.get_top_emoticon_users(guild_id=interaction.guild.id, limit=10)
    top_emoticons = await database.get_top_emoticons(guild_id=interaction.guild.id, limit=10)

    embed = discord.Embed(
        title=f"😊 ASCII Emoticon Leaderboard — {interaction.guild.name}",
        color=discord.Color.teal(),
        description=f"Tracked usages (`:D`, `:)`, `:>`, `^-^`, `^~^`, `^_^`, etc.) in <#{TARGET_CHANNEL_ID}>."
    )

    medals = ["🥇", "🥈", "🥉"]
    users_text = ""
    if not top_emoticon_users:
        users_text = "No ASCII emoticons recorded yet."
    else:
        for idx, (user_id, count) in enumerate(top_emoticon_users, start=1):
            rank = medals[idx - 1] if idx <= 3 else f"`#{idx}`"
            users_text += f"{rank} <@{user_id}>: **{count}** emoticons\n"

    embed.add_field(name="🏆 Top Emoticon Users", value=users_text, inline=False)

    if top_emoticons:
        emoticon_list = "\n".join([f"• `{emo}`: **{cnt}** times" for emo, cnt in top_emoticons])
        embed.add_field(name="🔥 Top Used ASCII Emoticons", value=emoticon_list, inline=False)

    embed.set_footer(text=f"Tracked channel ID: {TARGET_CHANNEL_ID}")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="stats", description="View reaction and ASCII emoticon stats for a user.")
@app_commands.describe(user="The user to view stats for (defaults to you)")
async def stats(interaction: discord.Interaction, user: discord.Member = None):
    """Displays detailed reaction and emoticon statistics for a specified user."""
    if not interaction.guild:
        await interaction.response.send_message("Stats are server-specific and cannot be run in DMs.", ephemeral=True)
        return

    target_user = user or interaction.user
    await interaction.response.defer()
    
    user_data = await database.get_user_stats(user_id=target_user.id, guild_id=interaction.guild.id)
    
    embed = discord.Embed(
        title=f"Reaction & Emoticon Stats — {target_user.display_name}",
        color=discord.Color.blue(),
        description=f"Tracked in <#{TARGET_CHANNEL_ID}>."
    )
    embed.set_thumbnail(url=target_user.display_avatar.url)
    
    embed.add_field(name="📤 Reactions Gave", value=f"**{user_data['gave']}**", inline=True)
    embed.add_field(name="📥 Reactions Received", value=f"**{user_data['received']}**", inline=True)
    embed.add_field(name="😊 Emoticons Used", value=f"**{user_data['emoticons_count']}**", inline=True)
    
    if user_data['top_gave_emojis']:
        top_gave_str = "\n".join([f"{emoji}: {count}" for emoji, count in user_data['top_gave_emojis']])
        embed.add_field(name="Most Used Emojis (Gave)", value=top_gave_str, inline=True)
        
    if user_data['top_received_emojis']:
        top_received_str = "\n".join([f"{emoji}: {count}" for emoji, count in user_data['top_received_emojis']])
        embed.add_field(name="Most Received Emojis", value=top_received_str, inline=True)
        
    if user_data['top_emoticons']:
        top_emoticon_str = "\n".join([f"`{emo}`: {count}" for emo, count in user_data['top_emoticons']])
        embed.add_field(name="Most Used Emoticons (ASCII)", value=top_emoticon_str, inline=False)
        
    embed.set_footer(text=f"Tracked channel ID: {TARGET_CHANNEL_ID}")
    await interaction.followup.send(embed=embed)

# ----------------- WHITELIST MANAGEMENT COMMANDS -----------------

whitelist_group = app_commands.Group(name="whitelist", description="Manage user whitelist for bot commands")

@whitelist_group.command(name="add", description="Add a user to the command whitelist")
@app_commands.describe(user="The user to add to the whitelist")
@app_commands.default_permissions(administrator=True)
async def whitelist_add(interaction: discord.Interaction, user: discord.User):
    if not can_manage_whitelist(interaction):
        await interaction.response.send_message("❌ You do not have permission to manage the whitelist.", ephemeral=True)
        return

    added = await database.add_to_whitelist(user.id)
    if added:
        await interaction.response.send_message(f"✅ Added {user.mention} (`{user.id}`) to the command whitelist.", ephemeral=True)
    else:
        await interaction.response.send_message(f"ℹ️ {user.mention} (`{user.id}`) is already in the database whitelist.", ephemeral=True)

@whitelist_group.command(name="remove", description="Remove a user from the command whitelist")
@app_commands.describe(user="The user to remove from the whitelist")
@app_commands.default_permissions(administrator=True)
async def whitelist_remove(interaction: discord.Interaction, user: discord.User):
    if not can_manage_whitelist(interaction):
        await interaction.response.send_message("❌ You do not have permission to manage the whitelist.", ephemeral=True)
        return

    removed = await database.remove_from_whitelist(user.id)
    env_ids = get_env_whitelisted_users()
    if user.id in env_ids:
        await interaction.response.send_message(
            f"⚠️ Removed {user.mention} (`{user.id}`) from database whitelist, but this user is also defined in `.env` (`WHITELISTED_USERS`). Remove them from `.env` to fully revoke access.",
            ephemeral=True
        )
    elif removed:
        await interaction.response.send_message(f"✅ Removed {user.mention} (`{user.id}`) from the command whitelist.", ephemeral=True)
    else:
        await interaction.response.send_message(f"ℹ️ {user.mention} (`{user.id}`) is not in the database whitelist.", ephemeral=True)

@whitelist_group.command(name="list", description="List all currently whitelisted users")
@app_commands.default_permissions(administrator=True)
async def whitelist_list(interaction: discord.Interaction):
    db_users = await database.get_whitelist()
    env_users = list(get_env_whitelisted_users())

    embed = discord.Embed(
        title="🛡️ Bot Command Whitelist",
        color=discord.Color.blue(),
        description="Users authorized to run bot slash commands."
    )

    if env_users:
        env_text = "\n".join([f"• <@{uid}> (`{uid}`)" for uid in env_users])
    else:
        env_text = "*None configured in .env*"
    embed.add_field(name="⚙️ Configured via `.env`", value=env_text, inline=False)

    if db_users:
        db_text = "\n".join([f"• <@{uid}> (`{uid}`)" for uid in db_users])
    else:
        db_text = "*No dynamic users added yet*"
    embed.add_field(name="💾 Added via Slash Commands (Database)", value=db_text, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

bot.tree.add_command(whitelist_group)


# ----------------- EXTERNAL APP / USER SLASH COMMANDS -----------------

@bot.tree.command(name="rate", description="Rates a user on a specified parameter with a random score.")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(parameter="The parameter or trait to rate the user on", user="The user to rate")
async def rate(interaction: discord.Interaction, parameter: str, user: discord.User):
    """Rates a user on a parameter with a random decimal from 0.01 to 100.00."""
    rating = round(random.uniform(0.01, 100.00), 2)
    
    embed = discord.Embed(
        title=f"{parameter} Scanner",
        description=f"{user.mention} is **{rating:.2f}%** {parameter}",
        color=discord.Color.purple()
    )
    if user.display_avatar:
        embed.set_thumbnail(url=user.display_avatar.url)
        
    await interaction.response.send_message(embed=embed)


if __name__ == "__main__":
    if not TOKEN:
        logger.error("DISCORD_TOKEN environment variable not set. Please check your .env file.")
    else:
        bot.run(TOKEN)

