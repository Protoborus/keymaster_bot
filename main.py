import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import asyncio
import logging
import db
from utils.database import Database
from utils.logger import setup_logger
from typing import cast

# Загрузка переменных окружения из .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = setup_logger()

# Проверка наличия токена бота в окружении
if not TOKEN:
    logger.error("DISCORD_TOKEN не задан. Укажите токен в файле .env (ключ DISCORD_TOKEN).")
    raise RuntimeError("DISCORD_TOKEN не задан")

# Приводим тип для статического анализатора: теперь TOKEN точно string
TOKEN = cast(str, TOKEN)

class KeyMasterBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True  # ЭТО ВАЖНО для работы с серверами и эмодзи
        intents.members = True # Желательно для профилей
        super().__init__(command_prefix="!", intents=intents)
        self.db = Database()  # Инициализация экземпляра базы данных

    async def setup_hook(self):
        # Инициализация базы данных
        await self.db.create_tables()  # Используем экземпляр базы данных

        # Загрузка когов
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                    logger.info(f"✅ Ког загружен: {filename}")
                except Exception as e:
                    logger.error(f"❌ Ошибка загрузки {filename}: {e}", exc_info=True)

        # Загрузка нового расширения cogs.keys
        try:
            await self.load_extension("cogs.keys")
            logger.info("✅ Ког загружен: keys")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки keys: {e}", exc_info=True)

        # Синхронизация слэш-команд
        try:
            await self.tree.sync()
            logger.info("🔁 Слэш-команды синхронизированы!")
        except Exception as e:
            logger.error(f"❌ Ошибка синхронизации слэш-команд: {e}", exc_info=True)

        # Регистрируем глобальный обработчик ошибок для слэш-команд на уровне Tree
        @self.tree.error
        async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
            logger.error(f"❌ Ошибка в команде {interaction.command.name if interaction.command else 'Unknown'}: {error}", exc_info=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"Произошла ошибка: {error}", ephemeral=True)
                else:
                    await interaction.followup.send(f"Произошла ошибка: {error}", ephemeral=True)
            except Exception:
                # Если отправка ответа упала — просто логируем
                logger.exception("Не удалось отправить сообщение об ошибке в интеракшн")

    async def on_ready(self):
        logger.info(f"🤖 Бот запущен как {self.user}")

async def main():
    # Запуск бота
    bot = KeyMasterBot()
    async with bot:
        await bot.start(TOKEN)  # type: ignore[arg-type]

if __name__ == "__main__":
    asyncio.run(main())