import aiosqlite
import os
import json


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
            # Таблица для активных LFG-сообщений (для восстановления view после рестарта)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS lfg_messages (
                    message_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    author_id INTEGER,
                    tank INTEGER,
                    healer INTEGER,
                    dps TEXT,
                    embed_json TEXT
                )
            ''')
            await db.commit()

            # Миграция: если таблица была старой версии, добавим колонку embed_json
            try:
                async with db.execute("PRAGMA table_info(lfg_messages)") as cursor:
                    cols = await cursor.fetchall()
                    col_names = [c[1] for c in cols]
                    if 'embed_json' not in col_names:
                        await db.execute('ALTER TABLE lfg_messages ADD COLUMN embed_json TEXT')
                        await db.commit()
            except Exception:
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

    # --- LFG persistence methods ---
    async def save_lfg(self, message_id: int, channel_id: int, author_id: int, tank: int | None = None, healer: int | None = None, dps: list | None = None, embed_json: str | None = None):
        dps_json = json.dumps(dps or [])
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''
                INSERT OR REPLACE INTO lfg_messages (message_id, channel_id, author_id, tank, healer, dps, embed_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (message_id, channel_id, author_id, tank, healer, dps_json, embed_json))
            await db.commit()

    async def get_active_lfgs(self):
        async with aiosqlite.connect(self.db_name) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT message_id, channel_id, author_id, tank, healer, dps, embed_json FROM lfg_messages') as cursor:
                rows = await cursor.fetchall()
                results = []
                for r in rows:
                    dps_list = json.loads(r['dps']) if r['dps'] else []
                    embed_dict = None
                    try:
                        embed_dict = json.loads(r['embed_json']) if r['embed_json'] else None
                    except Exception:
                        embed_dict = None
                    results.append((r['message_id'], r['channel_id'], r['author_id'], r['tank'], r['healer'], dps_list, embed_dict))
                return results

    async def update_lfg_slots(self, message_id: int, tank: int | None, healer: int | None, dps: list | None):
        dps_json = json.dumps(dps or [])
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('UPDATE lfg_messages SET tank = ?, healer = ?, dps = ? WHERE message_id = ?', (tank, healer, dps_json, message_id))
            await db.commit()

    async def delete_lfg(self, message_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('DELETE FROM lfg_messages WHERE message_id = ?', (message_id,))
            await db.commit()