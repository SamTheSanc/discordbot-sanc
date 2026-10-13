import os
import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("reaction_bot.verification")

DEFAULT_MEMBER_ROLE_ID = 1238766055908966492
DEFAULT_NEWCOMER_ROLE_ID = 1331556865037045813
DEFAULT_ADMIN_ROLE_ID = 1529365517247320114

def get_member_role_id() -> int:
    """Returns the Member role ID from environment variable or default."""
    try:
        return int(os.getenv("MEMBER_ROLE_ID", str(DEFAULT_MEMBER_ROLE_ID)))
    except ValueError:
        return DEFAULT_MEMBER_ROLE_ID

def get_newcomer_role_id() -> int:
    """Returns the Newcomer role ID from environment variable or default."""
    try:
        return int(os.getenv("NEWCOMER_ROLE_ID", str(DEFAULT_NEWCOMER_ROLE_ID)))
    except ValueError:
        return DEFAULT_NEWCOMER_ROLE_ID

def get_admin_role_id() -> int:
    """Returns the Admin / Authentication role ID from environment variable or default."""
    try:
        return int(os.getenv("ADMIN_ROLE_ID", str(DEFAULT_ADMIN_ROLE_ID)))
    except ValueError:
        return DEFAULT_ADMIN_ROLE_ID

# Aliases for backward compatibility
REQUIRED_STAFF_ROLE_ID = DEFAULT_ADMIN_ROLE_ID

def user_has_admin_role(user: discord.User | discord.Member, admin_role_id: int | None = None) -> bool:
    """Checks if a user has the configured admin/auth role."""
    if isinstance(user, discord.Member):
        target_role_id = admin_role_id if admin_role_id is not None else get_admin_role_id()
        return any(role.id == target_role_id for role in user.roles)
    return False

# Backward compatibility alias
user_has_staff_role = user_has_admin_role

async def check_admin_role(interaction: discord.Interaction, admin_role_id: int | None = None) -> bool:
    """Checks if user invoking the command has the admin role.
    If not, quietly informs them with an ephemeral message."""
    target_role_id = admin_role_id if admin_role_id is not None else get_admin_role_id()
    if not user_has_admin_role(interaction.user, target_role_id):
        await interaction.response.send_message(
            f"❌ You cannot use this command. You must have the <@&{target_role_id}> role.",
            ephemeral=True
        )
        return False
    return True

# Backward compatibility alias
check_staff_role = check_admin_role


async def find_most_recent_newcomer(guild: discord.Guild, newcomer_role_id: int) -> discord.Member | None:
    """Finds the most recently joined non-bot member in the guild who has the newcomer role."""
    if not guild.chunked:
        try:
            await guild.chunk()
        except Exception as e:
            logger.warning(f"Failed to chunk guild {guild.id}: {e}")

    candidates = [
        m for m in guild.members
        if not m.bot
        and any(r.id == newcomer_role_id for r in m.roles)
    ]

    if not candidates:
        return None

    # Sort descending by joined_at (or created_at if joined_at is None)
    candidates.sort(
        key=lambda m: (m.joined_at.timestamp() if m.joined_at else 0),
        reverse=True
    )
    return candidates[0]


class VerifyConfirmationView(discord.ui.View):
    """Confirmation buttons for the /verify slash command."""

    def __init__(
        self,
        author: discord.Member | discord.User,
        target: discord.Member,
        member_role_id: int,
        newcomer_role_id: int,
        admin_role_id: int | None = None,
        timeout: float = 60.0
    ):
        super().__init__(timeout=timeout)
        self.author = author
        self.target = target
        self.member_role_id = member_role_id
        self.newcomer_role_id = newcomer_role_id
        self.admin_role_id = admin_role_id if admin_role_id is not None else get_admin_role_id()
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not user_has_admin_role(interaction.user, self.admin_role_id):
            await interaction.response.send_message(
                f"❌ You cannot use this command. You must have the <@&{self.admin_role_id}> role.",
                ephemeral=True
            )
            return False
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ Only the user who ran `/verify` can confirm or cancel this action.",
                ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self.message:
            try:
                embed = self.message.embeds[0] if self.message.embeds else None
                if embed:
                    embed.color = discord.Color.dark_grey()
                    embed.set_footer(text="⏳ Verification timed out.")
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ This server is no longer available.", ephemeral=True)
            return

        newcomer_role = guild.get_role(self.newcomer_role_id)
        member_role = guild.get_role(self.member_role_id)

        if not newcomer_role or not member_role:
            await interaction.response.send_message(
                f"❌ Required roles not found. Please ensure Member role (`{self.member_role_id}`) "
                f"and Newcomer role (`{self.newcomer_role_id}`) exist in this server.",
                ephemeral=True
            )
            return

        # Fetch latest member object
        target_member = guild.get_member(self.target.id)
        if not target_member:
            try:
                target_member = await guild.fetch_member(self.target.id)
            except discord.NotFound:
                await interaction.response.send_message("❌ Target user has left the server.", ephemeral=True)
                return

        if not any(r.id == self.newcomer_role_id for r in target_member.roles):
            await interaction.response.send_message(
                f"❌ {target_member.mention} no longer has the Newcomer role.",
                ephemeral=True
            )
            return

        try:
            await target_member.remove_roles(
                newcomer_role,
                reason=f"Verified by {interaction.user} ({interaction.user.id})"
            )
            await target_member.add_roles(
                member_role,
                reason=f"Verified by {interaction.user} ({interaction.user.id})"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Bot lacks permission to manage roles. Please verify that the bot has 'Manage Roles' permission "
                "and its highest role is placed higher than Member and Newcomer in Server Settings -> Roles.",
                ephemeral=True
            )
            return
        except Exception as e:
            logger.error(f"Error updating roles for {target_member}: {e}", exc_info=e)
            await interaction.response.send_message(f"❌ Failed to update roles: {e}", ephemeral=True)
            return

        embed = discord.Embed(
            title="✅ User Verified",
            description=f"Successfully verified {target_member.mention}!\n\n"
                        f"• **Removed Role**: {newcomer_role.mention}\n"
                        f"• **Granted Role**: {member_role.mention}",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=target_member.display_avatar.url)
        embed.add_field(name="Username", value=f"`{target_member.name}`", inline=True)
        embed.add_field(name="User ID", value=f"`{target_member.id}`", inline=True)
        embed.add_field(name="Verified By", value=interaction.user.mention, inline=True)

        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❌ Verification Cancelled",
            description=f"Verification for {self.target.mention} (`{self.target.name}`) was cancelled by {interaction.user.mention}.",
            color=discord.Color.red()
        )
        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)


class UnverifyConfirmationView(discord.ui.View):
    """Confirmation buttons for the /unverify slash command."""

    def __init__(
        self,
        author: discord.Member | discord.User,
        target: discord.Member,
        member_role_id: int,
        newcomer_role_id: int,
        admin_role_id: int | None = None,
        timeout: float = 60.0
    ):
        super().__init__(timeout=timeout)
        self.author = author
        self.target = target
        self.member_role_id = member_role_id
        self.newcomer_role_id = newcomer_role_id
        self.admin_role_id = admin_role_id if admin_role_id is not None else get_admin_role_id()
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not user_has_admin_role(interaction.user, self.admin_role_id):
            await interaction.response.send_message(
                f"❌ You cannot use this command. You must have the <@&{self.admin_role_id}> role.",
                ephemeral=True
            )
            return False
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ Only the user who ran `/unverify` can confirm or cancel this action.",
                ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self.message:
            try:
                embed = self.message.embeds[0] if self.message.embeds else None
                if embed:
                    embed.color = discord.Color.dark_grey()
                    embed.set_footer(text="⏳ Unverification timed out.")
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass

    @discord.ui.button(label="Unverify", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ This server is no longer available.", ephemeral=True)
            return

        newcomer_role = guild.get_role(self.newcomer_role_id)
        member_role = guild.get_role(self.member_role_id)

        if not newcomer_role or not member_role:
            await interaction.response.send_message(
                f"❌ Required roles not found. Please ensure Member role (`{self.member_role_id}`) "
                f"and Newcomer role (`{self.newcomer_role_id}`) exist in this server.",
                ephemeral=True
            )
            return

        # Fetch latest member object
        target_member = guild.get_member(self.target.id)
        if not target_member:
            try:
                target_member = await guild.fetch_member(self.target.id)
            except discord.NotFound:
                await interaction.response.send_message("❌ Target user has left the server.", ephemeral=True)
                return

        if not any(r.id == self.member_role_id for r in target_member.roles):
            await interaction.response.send_message(
                f"❌ {target_member.mention} no longer has the Member role.",
                ephemeral=True
            )
            return

        try:
            await target_member.remove_roles(
                member_role,
                reason=f"Unverified by {interaction.user} ({interaction.user.id})"
            )
            await target_member.add_roles(
                newcomer_role,
                reason=f"Unverified by {interaction.user} ({interaction.user.id})"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Bot lacks permission to manage roles. Please verify that the bot has 'Manage Roles' permission "
                "and its highest role is placed higher than Member and Newcomer in Server Settings -> Roles.",
                ephemeral=True
            )
            return
        except Exception as e:
            logger.error(f"Error updating roles for {target_member}: {e}", exc_info=e)
            await interaction.response.send_message(f"❌ Failed to update roles: {e}", ephemeral=True)
            return

        embed = discord.Embed(
            title="⚠️ User Unverified",
            description=f"Successfully unverified {target_member.mention}!\n\n"
                        f"• **Removed Role**: {member_role.mention}\n"
                        f"• **Granted Role**: {newcomer_role.mention}",
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=target_member.display_avatar.url)
        embed.add_field(name="Username", value=f"`{target_member.name}`", inline=True)
        embed.add_field(name="User ID", value=f"`{target_member.id}`", inline=True)
        embed.add_field(name="Unverified By", value=interaction.user.mention, inline=True)

        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❌ Unverification Cancelled",
            description=f"Unverification for {self.target.mention} (`{self.target.name}`) was cancelled by {interaction.user.mention}.",
            color=discord.Color.red()
        )
        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)


def setup_verification_commands(bot: commands.Bot, admin_role_id: int | None = None):
    """Registers /verify and /unverify slash commands to the bot tree."""

    @bot.tree.command(name="verify", description="Verify a member: removes Newcomer and grants Member role.")
    @app_commands.describe(user="The member to verify (optional; defaults to the most recently joined newcomer)")
    @app_commands.default_permissions(manage_roles=True)
    async def verify(interaction: discord.Interaction, user: discord.Member | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        configured_admin_role_id = admin_role_id if admin_role_id is not None else get_admin_role_id()
        if not await check_admin_role(interaction, configured_admin_role_id):
            return

        member_role_id = get_member_role_id()
        newcomer_role_id = get_newcomer_role_id()

        target = user
        if target is None:
            target = await find_most_recent_newcomer(interaction.guild, newcomer_role_id)
            if target is None:
                await interaction.response.send_message(
                    f"❌ No member with the Newcomer role (<@&{newcomer_role_id}>) was found to verify.",
                    ephemeral=True
                )
                return
        else:
            has_newcomer = any(r.id == newcomer_role_id for r in target.roles)
            if not has_newcomer:
                has_member = any(r.id == member_role_id for r in target.roles)
                if has_member:
                    await interaction.response.send_message(
                        f"ℹ️ {target.mention} already has the Member role (<@&{member_role_id}>).",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"❌ {target.mention} does not have the Newcomer role (<@&{newcomer_role_id}>).",
                        ephemeral=True
                    )
                return

        embed = discord.Embed(
            title="Verification Confirmation",
            description=f"Are you sure you want to verify {target.mention}?",
            color=discord.Color.blue()
        )
        embed.add_field(name="Username", value=f"`{target.name}`", inline=True)
        embed.add_field(name="Mention", value=target.mention, inline=True)
        embed.add_field(name="User ID", value=f"`{target.id}`", inline=True)
        if target.joined_at:
            embed.add_field(name="Joined Server", value=f"<t:{int(target.joined_at.timestamp())}:R>", inline=True)
        embed.add_field(
            name="Role Changes",
            value=f"• Remove: <@&{newcomer_role_id}>\n• Add: <@&{member_role_id}>",
            inline=False
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(
            text=f"Requested by {interaction.user.name}",
            icon_url=interaction.user.display_avatar.url
        )

        view = VerifyConfirmationView(
            author=interaction.user,
            target=target,
            member_role_id=member_role_id,
            newcomer_role_id=newcomer_role_id,
            admin_role_id=configured_admin_role_id
        )

        await interaction.response.send_message(embed=embed, view=view)
        try:
            view.message = await interaction.original_response()
        except Exception as e:
            logger.debug(f"Could not retrieve original response for timeout tracking: {e}")

    @bot.tree.command(name="unverify", description="Unverify a member: removes Member and grants Newcomer role.")
    @app_commands.describe(user="The member to unverify (required; must have the Member role)")
    @app_commands.default_permissions(manage_roles=True)
    async def unverify(interaction: discord.Interaction, user: discord.Member):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        configured_admin_role_id = admin_role_id if admin_role_id is not None else get_admin_role_id()
        if not await check_admin_role(interaction, configured_admin_role_id):
            return

        member_role_id = get_member_role_id()
        newcomer_role_id = get_newcomer_role_id()

        has_member = any(r.id == member_role_id for r in user.roles)
        if not has_member:
            has_newcomer = any(r.id == newcomer_role_id for r in user.roles)
            if has_newcomer:
                await interaction.response.send_message(
                    f"ℹ️ {user.mention} is already unverified (has the Newcomer role <@&{newcomer_role_id}>).",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ {user.mention} does not have the Member role (<@&{member_role_id}>).",
                    ephemeral=True
                )
            return

        embed = discord.Embed(
            title="Unverification Confirmation",
            description=f"Are you sure you want to unverify {user.mention}?",
            color=discord.Color.gold()
        )
        embed.add_field(name="Username", value=f"`{user.name}`", inline=True)
        embed.add_field(name="Mention", value=user.mention, inline=True)
        embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
        if user.joined_at:
            embed.add_field(name="Joined Server", value=f"<t:{int(user.joined_at.timestamp())}:R>", inline=True)
        embed.add_field(
            name="Role Changes",
            value=f"• Remove: <@&{member_role_id}>\n• Add: <@&{newcomer_role_id}>",
            inline=False
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(
            text=f"Requested by {interaction.user.name}",
            icon_url=interaction.user.display_avatar.url
        )

        view = UnverifyConfirmationView(
            author=interaction.user,
            target=user,
            member_role_id=member_role_id,
            newcomer_role_id=newcomer_role_id,
            admin_role_id=configured_admin_role_id
        )

        await interaction.response.send_message(embed=embed, view=view)
        try:
            view.message = await interaction.original_response()
        except Exception as e:
            logger.debug(f"Could not retrieve original response for timeout tracking: {e}")
