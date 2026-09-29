import os
import logging
import random
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import database
from emoticons import extract_emoticons

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("reaction_bot")

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("COMMAND_PREFIX", "!")
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "1238775030444326952"))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True
intents.guilds = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=commands.DefaultHelpCommand())

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

    await bot.process_commands(message)

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

# ----------------- COMMANDS -----------------

@bot.hybrid_command(name="scan", description="Scan past messages in the allowed channel to index reactions and emoticons.")
@commands.has_permissions(administrator=True)
async def scan_channel(ctx: commands.Context, limit: int = 100):
    """Scans the allowed channel's past messages for reactions and ASCII emoticons."""
    if not ctx.guild:
        await ctx.send("This command can only be used in a server.")
        return

    await ctx.defer()
    
    target_channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not target_channel:
        try:
            target_channel = await bot.fetch_channel(TARGET_CHANNEL_ID)
        except Exception as e:
            await ctx.send(f"❌ Unable to access target channel (`{TARGET_CHANNEL_ID}`): {e}")
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
                    guild_id=ctx.guild.id,
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
                    guild_id=ctx.guild.id,
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
    await ctx.send(embed=embed)

@bot.hybrid_command(name="leaderboard", description="View server top users by reactions and emoticons.")
async def leaderboard(ctx: commands.Context):
    """Displays leaderboards for reactions gave/received and emoticons used."""
    if not ctx.guild:
        await ctx.send("Leaderboards are server-specific and cannot be run in DMs.")
        return

    await ctx.defer()
    
    top_givers = await database.get_top_givers(guild_id=ctx.guild.id, limit=10)
    top_receivers = await database.get_top_receivers(guild_id=ctx.guild.id, limit=10)
    top_emoticon_users = await database.get_top_emoticon_users(guild_id=ctx.guild.id, limit=10)
    top_emoticons = await database.get_top_emoticons(guild_id=ctx.guild.id, limit=5)
    
    embed = discord.Embed(
        title=f"🏆 Server Leaderboard — {ctx.guild.name}",
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
    await ctx.send(embed=embed)

@bot.hybrid_command(name="emoticons", description="View ASCII emoticon leaderboard and most used emoticons.")
async def emoticons_leaderboard(ctx: commands.Context):
    """Displays dedicated ASCII emoticon leaderboard."""
    if not ctx.guild:
        await ctx.send("Leaderboards are server-specific and cannot be run in DMs.")
        return

    await ctx.defer()
    top_emoticon_users = await database.get_top_emoticon_users(guild_id=ctx.guild.id, limit=10)
    top_emoticons = await database.get_top_emoticons(guild_id=ctx.guild.id, limit=10)

    embed = discord.Embed(
        title=f"😊 ASCII Emoticon Leaderboard — {ctx.guild.name}",
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
    await ctx.send(embed=embed)

@bot.hybrid_command(name="stats", description="View reaction and ASCII emoticon stats for a user.")
async def stats(ctx: commands.Context, user: discord.Member = None):
    """Displays detailed reaction and emoticon statistics for a specified user."""
    if not ctx.guild:
        await ctx.send("Stats are server-specific and cannot be run in DMs.")
        return

    target_user = user or ctx.author
    await ctx.defer()
    
    user_data = await database.get_user_stats(user_id=target_user.id, guild_id=ctx.guild.id)
    
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
    await ctx.send(embed=embed)


# ----------------- EXTERNAL APP / USER SLASH COMMANDS -----------------

@bot.tree.command(name="rate", description="Rates a user on a specified parameter with a random score.")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(parameter="The parameter or trait to rate the user on", user="The user to rate")
async def rate(interaction: discord.Interaction, parameter: str, user: discord.User):
    """Rates a user on a parameter with a random decimal from 0.01 to 100.00."""
    rating = round(random.uniform(0.01, 100.00), 2)
    
    embed = discord.Embed(
        title="🎲 Rating Generator",
        description=f"{user.mention} is **{rating:.2f}** {parameter}",
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

