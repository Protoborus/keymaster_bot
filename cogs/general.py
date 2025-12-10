import discord
from discord.ext import commands
from discord import app_commands
import io

class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Проверить задержку бота")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)  # Задержка в миллисекундах
        await interaction.response.send_message(f"Pong! Задержка: {latency} мс")

    async def get_emojis(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Команда работает только на сервере.", ephemeral=True)
            return

        # Даем боту время на загрузку
        await interaction.response.defer(ephemeral=True)

        try:
            # Прямой запрос к API сервера для получения актуального списка
            emojis = await interaction.guild.fetch_emojis()

            if not emojis:
                await interaction.followup.send("На этом сервере нет эмодзи.")
                return

            # Формируем текст
            output_text = "Скопируйте эти строки в cogs/keys.py:\n\n"
            for emoji in emojis:
                output_text += f'"{emoji.name}": "<:{emoji.name}:{emoji.id}>",\n'

            # Отправляем файл
            buffer = io.BytesIO(output_text.encode('utf-8'))
            file = discord.File(buffer, filename="emojis.txt")
            
            await interaction.followup.send(f"✅ Успешно загружено {len(emojis)} иконок:", file=file)

        except Exception as e:
            await interaction.followup.send(f"Ошибка: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))