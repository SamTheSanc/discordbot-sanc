import aiosqlite
import os

DB_PATH = os.getenv("DB_PATH", "data/reactions.db")

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reactions (
                message_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL DEFAULT 0,
                giver_id INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                emoji TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (message_id, giver_id, emoji)
            )
        """)
        
        # Check if guild_id column exists (migration for existing DBs)
        async with db.execute("PRAGMA table_info(reactions)") as cursor:
            columns = [column[1] for column in await cursor.fetchall()]
            if "guild_id" not in columns:
                await db.execute("ALTER TABLE reactions ADD COLUMN guild_id INTEGER NOT NULL DEFAULT 0")

        await db.execute("CREATE INDEX IF NOT EXISTS idx_giver ON reactions(giver_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_receiver ON reactions(receiver_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_guild ON reactions(guild_id)")

        # Drop alliances table if exists to clean up associated data
        await db.execute("DROP TABLE IF EXISTS alliances")

        await db.commit()

async def add_reaction(message_id: int, channel_id: int, guild_id: int, giver_id: int, receiver_id: int, emoji: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO reactions (message_id, channel_id, guild_id, giver_id, receiver_id, emoji)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, channel_id, guild_id, giver_id, receiver_id, emoji)
        )
        await db.commit()

async def remove_reaction(message_id: int, giver_id: int, emoji: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM reactions WHERE message_id = ? AND giver_id = ? AND emoji = ?",
            (message_id, giver_id, emoji)
        )
        await db.commit()

async def clear_message_reactions(message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM reactions WHERE message_id = ?", (message_id,))
        await db.commit()

async def clear_emoji_reactions(message_id: int, emoji: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM reactions WHERE message_id = ? AND emoji = ?",
            (message_id, emoji)
        )
        await db.commit()

async def get_top_givers(guild_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT giver_id, COUNT(*) as count 
            FROM reactions 
            WHERE guild_id = ?
            GROUP BY giver_id 
            ORDER BY count DESC 
            LIMIT ?
            """,
            (guild_id, limit)
        ) as cursor:
            return await cursor.fetchall()

async def get_top_receivers(guild_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT receiver_id, COUNT(*) as count 
            FROM reactions 
            WHERE guild_id = ?
            GROUP BY receiver_id 
            ORDER BY count DESC 
            LIMIT ?
            """,
            (guild_id, limit)
        ) as cursor:
            return await cursor.fetchall()

async def get_user_stats(user_id: int, guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        # Count gave in server
        async with db.execute("SELECT COUNT(*) FROM reactions WHERE giver_id = ? AND guild_id = ?", (user_id, guild_id)) as cursor:
            gave_row = await cursor.fetchone()
            gave_count = gave_row[0] if gave_row else 0

        # Count received in server
        async with db.execute("SELECT COUNT(*) FROM reactions WHERE receiver_id = ? AND guild_id = ?", (user_id, guild_id)) as cursor:
            received_row = await cursor.fetchone()
            received_count = received_row[0] if received_row else 0

        # Top emojis gave in server
        async with db.execute(
            """
            SELECT emoji, COUNT(*) as count 
            FROM reactions 
            WHERE giver_id = ? AND guild_id = ?
            GROUP BY emoji 
            ORDER BY count DESC 
            LIMIT 3
            """,
            (user_id, guild_id)
        ) as cursor:
            top_gave_emojis = await cursor.fetchall()

        # Top emojis received in server
        async with db.execute(
            """
            SELECT emoji, COUNT(*) as count 
            FROM reactions 
            WHERE receiver_id = ? AND guild_id = ?
            GROUP BY emoji 
            ORDER BY count DESC 
            LIMIT 3
            """,
            (user_id, guild_id)
        ) as cursor:
            top_received_emojis = await cursor.fetchall()

        return {
            "gave": gave_count,
            "received": received_count,
            "top_gave_emojis": top_gave_emojis,
            "top_received_emojis": top_received_emojis
        }

