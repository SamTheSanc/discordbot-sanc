import aiosqlite
import os

DB_PATH = os.getenv("DB_PATH", "data/reactions.db")
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "1238775030444326952"))

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
        await db.execute("CREATE INDEX IF NOT EXISTS idx_channel ON reactions(channel_id)")

        # Create emoticons table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS emoticons (
                message_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL DEFAULT 0,
                user_id INTEGER NOT NULL,
                emoticon TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (message_id, emoticon)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_emoticon_user ON emoticons(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_emoticon_guild ON emoticons(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_emoticon_channel ON emoticons(channel_id)")

        # Drop legacy alliances table if exists
        await db.execute("DROP TABLE IF EXISTS alliances")

        # Purge any legacy records outside TARGET_CHANNEL_ID to ensure strict single-channel counting
        await db.execute("DELETE FROM reactions WHERE channel_id != ?", (TARGET_CHANNEL_ID,))
        await db.execute("DELETE FROM emoticons WHERE channel_id != ?", (TARGET_CHANNEL_ID,))

        await db.commit()

async def add_reaction(message_id: int, channel_id: int, guild_id: int, giver_id: int, receiver_id: int, emoji: str):
    if channel_id != TARGET_CHANNEL_ID:
        return
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

# --- Emoticon database operations ---

async def record_emoticons(message_id: int, channel_id: int, guild_id: int, user_id: int, emoticons: dict[str, int]):
    if channel_id != TARGET_CHANNEL_ID or not emoticons:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM emoticons WHERE message_id = ?", (message_id,))
        for emoticon, count in emoticons.items():
            await db.execute(
                """
                INSERT OR REPLACE INTO emoticons (message_id, channel_id, guild_id, user_id, emoticon, count)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, channel_id, guild_id, user_id, emoticon, count)
            )
        await db.commit()

async def delete_message_emoticons(message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM emoticons WHERE message_id = ?", (message_id,))
        await db.commit()

# --- Leaderboard & Stats queries (Strictly restricted to TARGET_CHANNEL_ID) ---

async def get_top_givers(guild_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT giver_id, COUNT(*) as count 
            FROM reactions 
            WHERE guild_id = ? AND channel_id = ?
            GROUP BY giver_id 
            ORDER BY count DESC 
            LIMIT ?
            """,
            (guild_id, TARGET_CHANNEL_ID, limit)
        ) as cursor:
            return await cursor.fetchall()

async def get_top_receivers(guild_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT receiver_id, COUNT(*) as count 
            FROM reactions 
            WHERE guild_id = ? AND channel_id = ?
            GROUP BY receiver_id 
            ORDER BY count DESC 
            LIMIT ?
            """,
            (guild_id, TARGET_CHANNEL_ID, limit)
        ) as cursor:
            return await cursor.fetchall()

async def get_top_emoticon_users(guild_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT user_id, SUM(count) as total 
            FROM emoticons 
            WHERE guild_id = ? AND channel_id = ?
            GROUP BY user_id 
            ORDER BY total DESC 
            LIMIT ?
            """,
            (guild_id, TARGET_CHANNEL_ID, limit)
        ) as cursor:
            return await cursor.fetchall()

async def get_top_emoticons(guild_id: int, limit: int = 5):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT emoticon, SUM(count) as total 
            FROM emoticons 
            WHERE guild_id = ? AND channel_id = ?
            GROUP BY emoticon 
            ORDER BY total DESC 
            LIMIT ?
            """,
            (guild_id, TARGET_CHANNEL_ID, limit)
        ) as cursor:
            return await cursor.fetchall()

async def get_user_stats(user_id: int, guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        # Count gave in server channel
        async with db.execute(
            "SELECT COUNT(*) FROM reactions WHERE giver_id = ? AND guild_id = ? AND channel_id = ?",
            (user_id, guild_id, TARGET_CHANNEL_ID)
        ) as cursor:
            gave_row = await cursor.fetchone()
            gave_count = gave_row[0] if gave_row else 0

        # Count received in server channel
        async with db.execute(
            "SELECT COUNT(*) FROM reactions WHERE receiver_id = ? AND guild_id = ? AND channel_id = ?",
            (user_id, guild_id, TARGET_CHANNEL_ID)
        ) as cursor:
            received_row = await cursor.fetchone()
            received_count = received_row[0] if received_row else 0

        # Top emojis gave in server channel
        async with db.execute(
            """
            SELECT emoji, COUNT(*) as count 
            FROM reactions 
            WHERE giver_id = ? AND guild_id = ? AND channel_id = ?
            GROUP BY emoji 
            ORDER BY count DESC 
            LIMIT 3
            """,
            (user_id, guild_id, TARGET_CHANNEL_ID)
        ) as cursor:
            top_gave_emojis = await cursor.fetchall()

        # Top emojis received in server channel
        async with db.execute(
            """
            SELECT emoji, COUNT(*) as count 
            FROM reactions 
            WHERE receiver_id = ? AND guild_id = ? AND channel_id = ?
            GROUP BY emoji 
            ORDER BY count DESC 
            LIMIT 3
            """,
            (user_id, guild_id, TARGET_CHANNEL_ID)
        ) as cursor:
            top_received_emojis = await cursor.fetchall()

        # Total emoticons used by user in server channel
        async with db.execute(
            "SELECT COALESCE(SUM(count), 0) FROM emoticons WHERE user_id = ? AND guild_id = ? AND channel_id = ?",
            (user_id, guild_id, TARGET_CHANNEL_ID)
        ) as cursor:
            emoticon_row = await cursor.fetchone()
            emoticons_count = emoticon_row[0] if emoticon_row else 0

        # Top emoticons used by user in server channel
        async with db.execute(
            """
            SELECT emoticon, SUM(count) as total 
            FROM emoticons 
            WHERE user_id = ? AND guild_id = ? AND channel_id = ?
            GROUP BY emoticon 
            ORDER BY total DESC 
            LIMIT 5
            """,
            (user_id, guild_id, TARGET_CHANNEL_ID)
        ) as cursor:
            top_emoticons = await cursor.fetchall()

        return {
            "gave": gave_count,
            "received": received_count,
            "top_gave_emojis": top_gave_emojis,
            "top_received_emojis": top_received_emojis,
            "emoticons_count": emoticons_count,
            "top_emoticons": top_emoticons
        }
