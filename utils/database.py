import aiosqlite
import os


class Database:
    def __init__(self, db_name: str = 'bot.db'):
        self.db_name = db_name

    async def create_tables(self):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    discord_id INTEGER PRIMARY KEY,
                    character_name TEXT,
                    realm_slug TEXT,
                    region TEXT,
                    rio_score REAL DEFAULT 0,
                    character_class TEXT,
                    thumbnail_url TEXT,
                    item_level INTEGER,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await db.commit()
            print(f"[INFO] База данных {self.db_name} проверена/создана.")

            # Миграция: убедимся, что колонка item_level существует (для старых БД)
            try:
                async with db.execute("PRAGMA table_info(users)") as cursor:
                    cols = await cursor.fetchall()
                    col_names = [c[1] for c in cols]
                    if 'item_level' not in col_names:
                        await db.execute('ALTER TABLE users ADD COLUMN item_level INTEGER')
                        await db.commit()
            except Exception:
                # Не критично, продолжаем
                pass

    async def register_user(self, discord_id, name, realm, region, score, char_class, thumbnail, item_level=None):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''
                INSERT OR REPLACE INTO users 
                (discord_id, character_name, realm_slug, region, rio_score, character_class, thumbnail_url, item_level, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (discord_id, name, realm, region, score, char_class, thumbnail, item_level))
            await db.commit()

    async def get_user(self, discord_id):
        async with aiosqlite.connect(self.db_name) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT discord_id, character_name, realm_slug, region, rio_score, character_class, thumbnail_url, item_level FROM users WHERE discord_id = ?', (discord_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    # Возвращаем кортеж для совместимости с существующими вызовами кода
                    return tuple(row)
                return None

    async def get_all_users(self):
        async with aiosqlite.connect(self.db_name) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT discord_id, character_name, realm_slug, region FROM users') as cursor:
                rows = await cursor.fetchall()
                return [tuple(row) for row in rows]

    async def get_top_users(self, limit=10):
        async with aiosqlite.connect(self.db_name) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT character_name, realm_slug, rio_score, character_class FROM users ORDER BY rio_score DESC LIMIT ?', (limit,)) as cursor:
                rows = await cursor.fetchall()
                return [tuple(row) for row in rows]