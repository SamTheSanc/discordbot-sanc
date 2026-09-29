import os
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv

import database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("reaction_bot")

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("COMMAND_PREFIX", "!")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True
intents.guilds = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=commands.DefaultHelpCommand())

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await database.init_db()
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    # Ignore reactions in DMs
    if not payload.guild_id:
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
    try:
        await database.clear_message_reactions(payload.message_id)
    except Exception as e:
        logger.error(f"Error handling reaction clear: {e}")

@bot.event
async def on_raw_reaction_clear_emoji(payload: discord.RawReactionClearEmojiEvent):
    try:
        await database.clear_emoji_reactions(payload.message_id, str(payload.emoji))
    except Exception as e:
        logger.error(f"Error handling reaction clear emoji: {e}")

# ----------------- REACTION COMMANDS -----------------

@bot.hybrid_command(name="scan", description="Scan past messages in the channel to index existing reactions.")
@commands.has_permissions(administrator=True)
async def scan_channel(ctx: commands.Context, limit: int = 100):
    """Scans the current channel's past messages for reactions."""
    if not ctx.guild:
        await ctx.send("This command can only be used in a server channel.")
        return

    await ctx.defer()
    
    count_messages = 0
    count_reactions = 0
    
    async for message in ctx.channel.history(limit=limit):
        count_messages += 1
        receiver_id = message.author.id
        for reaction in message.reactions:
            emoji_str = str(reaction.emoji)
            async for user in reaction.users():
                await database.add_reaction(
                    message_id=message.id,
                    channel_id=ctx.channel.id,
                    guild_id=ctx.guild.id,
                    giver_id=user.id,
                    receiver_id=receiver_id,
                    emoji=emoji_str
                )
                count_reactions += 1
                
    embed = discord.Embed(
        title="Channel Scan Complete",
        description=f"Scanned **{count_messages}** messages and indexed **{count_reactions}** reactions in {ctx.channel.mention}.",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.hybrid_command(name="leaderboard", description="View server top users by reactions gave and received.")
async def leaderboard(ctx: commands.Context):
    """Displays leaderboards for reactions gave and received in this server."""
    if not ctx.guild:
        await ctx.send("Leaderboards are server-specific and cannot be run in DMs.")
        return

    await ctx.defer()
    
    top_givers = await database.get_top_givers(guild_id=ctx.guild.id, limit=10)
    top_receivers = await database.get_top_receivers(guild_id=ctx.guild.id, limit=10)
    
    embed = discord.Embed(
        title=f"🏆 Reaction Leaderboard — {ctx.guild.name}",
        color=discord.Color.gold(),
        description="Ranking of server members based on reactions **gave** and **received**."
    )
    
    medals = ["🥇", "🥈", "🥉"]
    
    # Format Top Givers
    givers_text = ""
    if not top_givers:
        givers_text = "No reactions recorded in this server yet."
    else:
        for idx, (user_id, count) in enumerate(top_givers, start=1):
            rank = medals[idx - 1] if idx <= 3 else f"`#{idx}`"
            givers_text += f"{rank} <@{user_id}>: **{count}** reactions gave\n"
            
    # Format Top Receivers
    receivers_text = ""
    if not top_receivers:
        receivers_text = "No reactions recorded in this server yet."
    else:
        for idx, (user_id, count) in enumerate(top_receivers, start=1):
            rank = medals[idx - 1] if idx <= 3 else f"`#{idx}`"
            receivers_text += f"{rank} <@{user_id}>: **{count}** reactions received\n"
            
    embed.add_field(name="📤 Top Reactions Gave", value=givers_text, inline=False)
    embed.add_field(name="📥 Top Reactions Received", value=receivers_text, inline=False)
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="stats", description="View server reaction stats for yourself or another user.")
async def stats(ctx: commands.Context, user: discord.Member = None):
    """Displays detailed reaction statistics for a specified user in this server."""
    if not ctx.guild:
        await ctx.send("Stats are server-specific and cannot be run in DMs.")
        return

    target_user = user or ctx.author
    await ctx.defer()
    
    user_data = await database.get_user_stats(user_id=target_user.id, guild_id=ctx.guild.id)
    
    embed = discord.Embed(
        title=f"Reaction Stats for {target_user.display_name} ({ctx.guild.name})",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=target_user.display_avatar.url)
    embed.add_field(name="📤 Reactions Gave", value=f"**{user_data['gave']}**", inline=True)
    embed.add_field(name="📥 Reactions Received", value=f"**{user_data['received']}**", inline=True)
    
    if user_data['top_gave_emojis']:
        top_gave_str = "\n".join([f"{emoji}: {count}" for emoji, count in user_data['top_gave_emojis']])
        embed.add_field(name="Most Used Emojis (Gave)", value=top_gave_str, inline=False)
        
    if user_data['top_received_emojis']:
        top_received_str = "\n".join([f"{emoji}: {count}" for emoji, count in user_data['top_received_emojis']])
        embed.add_field(name="Most Received Emojis", value=top_received_str, inline=False)
        
    await ctx.send(embed=embed)

# ----------------- ALLIANCE COMMANDS -----------------

@bot.hybrid_command(name="alliance_add", description="Add a server ID to an alliance.")
@commands.has_permissions(administrator=True)
async def alliance_add(ctx: commands.Context, alliance_name: str, server_id: str):
    """Adds a server ID to the specified alliance."""
    try:
        guild_id_int = int(server_id.strip())
    except ValueError:
        await ctx.send("❌ Please provide a valid numerical Server ID.", ephemeral=True)
        return

    await database.add_guild_to_alliance(alliance_name, guild_id_int)
    
    # Try fetching guild name if bot has access
    guild = bot.get_guild(guild_id_int)
    name_display = guild.name if guild else f"ID: {guild_id_int}"
    
    await ctx.send(f"✅ Added **{name_display}** (`{guild_id_int}`) to alliance **{alliance_name}**.")

@bot.hybrid_command(name="alliance_remove", description="Remove a server ID from an alliance.")
@commands.has_permissions(administrator=True)
async def alliance_remove(ctx: commands.Context, alliance_name: str, server_id: str):
    """Removes a server ID from the specified alliance."""
    try:
        guild_id_int = int(server_id.strip())
    except ValueError:
        await ctx.send("❌ Please provide a valid numerical Server ID.", ephemeral=True)
        return

    await database.remove_guild_from_alliance(alliance_name, guild_id_int)
    await ctx.send(f"🗑️ Removed server (`{guild_id_int}`) from alliance **{alliance_name}**.")

@bot.hybrid_command(name="alliance", description="View total members and servers in an alliance.")
async def alliance_info(ctx: commands.Context, alliance_name: str):
    """Shows total members and the list of servers in an alliance."""
    await ctx.defer()
    
    guild_ids = await database.get_alliance_guilds(alliance_name)
    if not guild_ids:
        await ctx.send(f"⚠️ Alliance **{alliance_name}** not found or has no servers added.", ephemeral=True)
        return

    servers_info = []
    total_members = 0

    for gid in guild_ids:
        guild = bot.get_guild(gid)
        member_count = 0
        guild_name = f"Unknown Server ({gid})"

        if guild:
            guild_name = guild.name
            member_count = guild.member_count or len(guild.members)
        else:
            # Attempt to fetch guild if not in cache
            try:
                fetched_guild = await bot.fetch_guild(gid, with_counts=True)
                guild_name = fetched_guild.name
                member_count = fetched_guild.approximate_member_count or 0
            except Exception:
                pass

        total_members += member_count
        servers_info.append({"name": guild_name, "count": member_count})

    # Sort servers by member count descending
    servers_info.sort(key=lambda x: x["count"], reverse=True)

    # Format list
    lines = [f"- {s['name']} ({s['count']:,})" for s in servers_info]
    servers_text = "\n".join(lines) if lines else "No servers found."

    embed = discord.Embed(
        title=f"🛡️ {alliance_name} ({total_members:,})",
        description=f"**{alliance_name} ({total_members:,})**\n\n{servers_text}",
        color=discord.Color.blue()
    )
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="alliance_list", description="List all registered alliances.")
async def alliance_list(ctx: commands.Context):
    """Lists all registered alliances."""
    await ctx.defer()
    alliances = await database.list_alliances()
    if not alliances:
        await ctx.send("No alliances created yet. Use `/alliance_add <name> <server_id>` to create one.")
        return

    alliance_lines = [f"• **{name}**" for name in alliances]
    embed = discord.Embed(
        title="Registered Alliances",
        description="\n".join(alliance_lines),
        color=discord.Color.purple()
    )
    await ctx.send(embed=embed)

if __name__ == "__main__":
    if not TOKEN:
        logger.error("DISCORD_TOKEN environment variable not set. Please check your .env file.")
    else:
        bot.run(TOKEN)
