import aiosqlite

DB_NAME = "bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                discord_id INTEGER PRIMARY KEY,
                region TEXT,
                realm TEXT,
                character_name TEXT,
                rio_score REAL,
                main_class TEXT,
                thumbnail_url TEXT
            )
            """
        )
        await db.commit()