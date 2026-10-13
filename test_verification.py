import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
import datetime

import discord
from verification import (
    DEFAULT_MEMBER_ROLE_ID,
    DEFAULT_NEWCOMER_ROLE_ID,
    DEFAULT_ADMIN_ROLE_ID,
    REQUIRED_STAFF_ROLE_ID,
    get_member_role_id,
    get_newcomer_role_id,
    get_admin_role_id,
    user_has_staff_role,
    user_has_admin_role,
    check_staff_role,
    check_admin_role,
    find_most_recent_newcomer,
    VerifyConfirmationView,
    UnverifyConfirmationView,
)

class TestVerification(unittest.IsolatedAsyncioTestCase):
    def test_role_id_defaults(self):
        self.assertEqual(get_member_role_id(), 1238766055908966492)
        self.assertEqual(get_newcomer_role_id(), 1331556865037045813)
        self.assertEqual(get_admin_role_id(), 1529365517247320114)
        self.assertEqual(DEFAULT_ADMIN_ROLE_ID, 1529365517247320114)
        self.assertEqual(REQUIRED_STAFF_ROLE_ID, 1529365517247320114)

    def test_user_has_staff_role(self):
        staff_role = MagicMock(spec=discord.Role)
        staff_role.id = REQUIRED_STAFF_ROLE_ID

        other_role = MagicMock(spec=discord.Role)
        other_role.id = 999999

        user_with_role = MagicMock(spec=discord.Member)
        user_with_role.roles = [other_role, staff_role]
        self.assertTrue(user_has_staff_role(user_with_role))

        user_without_role = MagicMock(spec=discord.Member)
        user_without_role.roles = [other_role]
        self.assertFalse(user_has_staff_role(user_without_role))

    async def test_check_staff_role_ephemeral(self):
        staff_role = MagicMock(spec=discord.Role)
        staff_role.id = REQUIRED_STAFF_ROLE_ID

        # Authorized interaction
        interaction_ok = MagicMock(spec=discord.Interaction)
        user_ok = MagicMock(spec=discord.Member)
        user_ok.roles = [staff_role]
        interaction_ok.user = user_ok
        self.assertTrue(await check_staff_role(interaction_ok))

        # Unauthorized interaction
        interaction_fail = MagicMock(spec=discord.Interaction)
        user_fail = MagicMock(spec=discord.Member)
        user_fail.roles = []
        interaction_fail.user = user_fail
        interaction_fail.response = MagicMock()
        interaction_fail.response.send_message = AsyncMock()

        self.assertFalse(await check_staff_role(interaction_fail))
        interaction_fail.response.send_message.assert_awaited_once()
        args, kwargs = interaction_fail.response.send_message.call_args
        self.assertTrue(kwargs.get("ephemeral"))
        self.assertIn("1529365517247320114", args[0])

    async def test_find_most_recent_newcomer(self):
        guild = MagicMock(spec=discord.Guild)
        guild.chunked = True
        
        role_newcomer = MagicMock(spec=discord.Role)
        role_newcomer.id = DEFAULT_NEWCOMER_ROLE_ID
        
        role_other = MagicMock(spec=discord.Role)
        role_other.id = 999999999

        # Member 1: joined earlier, has newcomer role
        m1 = MagicMock(spec=discord.Member)
        m1.bot = False
        m1.roles = [role_newcomer]
        m1.joined_at = datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)

        # Member 2: joined later, has newcomer role
        m2 = MagicMock(spec=discord.Member)
        m2.bot = False
        m2.roles = [role_newcomer]
        m2.joined_at = datetime.datetime(2026, 1, 2, 12, 0, tzinfo=datetime.timezone.utc)

        # Member 3: joined even later, but is a bot
        m3 = MagicMock(spec=discord.Member)
        m3.bot = True
        m3.roles = [role_newcomer]
        m3.joined_at = datetime.datetime(2026, 1, 3, 12, 0, tzinfo=datetime.timezone.utc)

        # Member 4: joined later, but does NOT have newcomer role
        m4 = MagicMock(spec=discord.Member)
        m4.bot = False
        m4.roles = [role_other]
        m4.joined_at = datetime.datetime(2026, 1, 4, 12, 0, tzinfo=datetime.timezone.utc)

        guild.members = [m1, m2, m3, m4]

        recent = await find_most_recent_newcomer(guild, DEFAULT_NEWCOMER_ROLE_ID)
        self.assertIsNotNone(recent)
        self.assertEqual(recent, m2)

    async def test_verify_confirmation_view_confirm(self):
        staff_role = MagicMock(spec=discord.Role)
        staff_role.id = REQUIRED_STAFF_ROLE_ID

        author = MagicMock(spec=discord.Member)
        author.id = 111
        author.name = "ModUser"
        author.roles = [staff_role]

        target = MagicMock(spec=discord.Member)
        target.id = 222
        target.name = "TargetUser"
        target.mention = "<@222>"
        target.display_avatar = MagicMock()
        target.display_avatar.url = "https://example.com/avatar.png"
        target.remove_roles = AsyncMock()
        target.add_roles = AsyncMock()

        role_newcomer = MagicMock(spec=discord.Role)
        role_newcomer.id = DEFAULT_NEWCOMER_ROLE_ID
        role_newcomer.name = "Newcomer"
        role_newcomer.mention = f"<@&{DEFAULT_NEWCOMER_ROLE_ID}>"

        role_member = MagicMock(spec=discord.Role)
        role_member.id = DEFAULT_MEMBER_ROLE_ID
        role_member.name = "Member"
        role_member.mention = f"<@&{DEFAULT_MEMBER_ROLE_ID}>"

        target.roles = [role_newcomer]

        guild = MagicMock(spec=discord.Guild)
        guild.get_role.side_effect = lambda rid: role_member if rid == DEFAULT_MEMBER_ROLE_ID else (role_newcomer if rid == DEFAULT_NEWCOMER_ROLE_ID else None)
        guild.get_member.return_value = target

        view = VerifyConfirmationView(
            author=author,
            target=target,
            member_role_id=DEFAULT_MEMBER_ROLE_ID,
            newcomer_role_id=DEFAULT_NEWCOMER_ROLE_ID
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = author
        interaction.guild = guild
        interaction.response = MagicMock()
        interaction.response.edit_message = AsyncMock()

        # Check view interaction check passes for author with staff role
        self.assertTrue(await view.interaction_check(interaction))

        # Check view interaction check fails for user without staff role
        unauth_user = MagicMock(spec=discord.Member)
        unauth_user.id = 999
        unauth_user.roles = []
        interaction_unauth = MagicMock(spec=discord.Interaction)
        interaction_unauth.user = unauth_user
        interaction_unauth.response = MagicMock()
        interaction_unauth.response.send_message = AsyncMock()
        self.assertFalse(await view.interaction_check(interaction_unauth))
        interaction_unauth.response.send_message.assert_awaited_once()
        self.assertTrue(interaction_unauth.response.send_message.call_args[1].get("ephemeral"))

        # Call confirm button callback
        button = MagicMock(spec=discord.ui.Button)
        await VerifyConfirmationView.confirm(view, interaction, button)

        target.remove_roles.assert_awaited_once_with(
            role_newcomer,
            reason=f"Verified by {author} ({author.id})"
        )
        target.add_roles.assert_awaited_once_with(
            role_member,
            reason=f"Verified by {author} ({author.id})"
        )
        interaction.response.edit_message.assert_awaited_once()

    async def test_unverify_confirmation_view_confirm(self):
        staff_role = MagicMock(spec=discord.Role)
        staff_role.id = REQUIRED_STAFF_ROLE_ID

        author = MagicMock(spec=discord.Member)
        author.id = 111
        author.name = "ModUser"
        author.roles = [staff_role]

        target = MagicMock(spec=discord.Member)
        target.id = 333
        target.name = "MemberUser"
        target.mention = "<@333>"
        target.display_avatar = MagicMock()
        target.display_avatar.url = "https://example.com/avatar.png"
        target.remove_roles = AsyncMock()
        target.add_roles = AsyncMock()

        role_newcomer = MagicMock(spec=discord.Role)
        role_newcomer.id = DEFAULT_NEWCOMER_ROLE_ID
        role_newcomer.name = "Newcomer"
        role_newcomer.mention = f"<@&{DEFAULT_NEWCOMER_ROLE_ID}>"

        role_member = MagicMock(spec=discord.Role)
        role_member.id = DEFAULT_MEMBER_ROLE_ID
        role_member.name = "Member"
        role_member.mention = f"<@&{DEFAULT_MEMBER_ROLE_ID}>"

        target.roles = [role_member]

        guild = MagicMock(spec=discord.Guild)
        guild.get_role.side_effect = lambda rid: role_member if rid == DEFAULT_MEMBER_ROLE_ID else (role_newcomer if rid == DEFAULT_NEWCOMER_ROLE_ID else None)
        guild.get_member.return_value = target

        view = UnverifyConfirmationView(
            author=author,
            target=target,
            member_role_id=DEFAULT_MEMBER_ROLE_ID,
            newcomer_role_id=DEFAULT_NEWCOMER_ROLE_ID
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = author
        interaction.guild = guild
        interaction.response = MagicMock()
        interaction.response.edit_message = AsyncMock()

        self.assertTrue(await view.interaction_check(interaction))

        # Call confirm button callback
        button = MagicMock(spec=discord.ui.Button)
        await UnverifyConfirmationView.confirm(view, interaction, button)

        target.remove_roles.assert_awaited_once_with(
            role_member,
            reason=f"Unverified by {author} ({author.id})"
        )
        target.add_roles.assert_awaited_once_with(
            role_newcomer,
            reason=f"Unverified by {author} ({author.id})"
        )
        interaction.response.edit_message.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
