import aiosqlite

class Database:
    def __init__(self, db_name='bot_database.db'):
        self.db_name = db_name

    async def create_tables(self):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    discord_id INTEGER PRIMARY KEY,
                    character_name TEXT,
                    realm_slug TEXT,
                    region TEXT,
                    rio_score REAL,
                    character_class TEXT,
                    thumbnail_url TEXT
                )
                """
            )
            await db.commit()

    async def register_user(self, discord_id: int, name: str, realm: str, region: str, score: float, char_class: str, thumbnail: str):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO users (discord_id, character_name, realm_slug, region, rio_score, character_class, thumbnail_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (discord_id, name, realm, region, score, char_class, thumbnail)
            )
            await db.commit()

    async def get_user(self, discord_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute(
                "SELECT discord_id, character_name, realm_slug, region, rio_score, character_class, thumbnail_url FROM users WHERE discord_id = ?",
                (discord_id,)
            ) as cursor:
                return await cursor.fetchone()

    async def get_all_users(self):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute(
                "SELECT discord_id, character_name, realm_slug, region FROM users"
            ) as cursor:
                return await cursor.fetchall()

    async def get_top_users(self, limit=10):
        async with aiosqlite.connect(self.db_name) as db:
            # Сортируем по rio_score
            async with db.execute(
                "SELECT character_name, realm_slug, rio_score, character_class FROM users ORDER BY rio_score DESC LIMIT ?",
                (limit,)
            ) as cursor:
                return await cursor.fetchall()