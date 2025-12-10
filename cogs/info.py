import discord
from discord import app_commands
from discord.ext import commands
from utils.raiderio import get_weekly_affixes

# Словарь перевода аффиксов
AFFIX_TRANSLATIONS = {
    "Fortified": "Укрепленный",
    "Tyrannical": "Тиранический",
    "Challenger's Peril": "Риск претендента",
    "Xal'atath's Guile": "Вероломство Ксал'атат",
    "Xal'atath's Bargain: Ascendant": "Сделка с Ксал'атат: Вознесение",
    "Xal'atath's Bargain: Voidbound": "Сделка с Ксал'атат: Слуга Бездны",
    "Xal'atath's Bargain: Devour": "Сделка с Ксал'атат: Пожирание",
    "Xal'atath's Bargain: Oblivion": "Сделка с Ксал'атат: Забвение",
    "Xal'atath's Bargain: Pulsar": "Сделка с Ксал'атат: Пульсар"
}

class Info(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="helpme", description="Получить описание функционала бота в личные сообщения")
    async def helpme(self, interaction: discord.Interaction):
        text = (
            "Функционал KeyMasterBot:\n"
            "- /register — регистрация персонажа\n"
            "- /lfg — создать сбор в ключ\n"
            "- Кнопки для записи в роли (Танк, Хил, ДД)\n"
            "- Кнопка 'Закрыть сбор' для лидера\n"
            "- Автоматическая проверка лимитов\n"
            "- Примечание к сбору (опционально)\n"
            "- Восстановление сборов после рестарта\n"
            "- Профиль, рейтинг, gear через Raider.IO\n"
            "- Защита от дублей ролей\n"
            "- Слэш-команды и быстрые ответы\n"
        )
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.user.send(text)
            await interaction.followup.send("Функционал отправлен в личные сообщения!", ephemeral=True)
        except Exception:
            await interaction.followup.send("Не удалось отправить сообщение в ЛС. Откройте личные сообщения для сервера!", ephemeral=True)

    @app_commands.command(name="affixes", description="Показать аффиксы текущей недели")
    async def affixes(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            data = await get_weekly_affixes('eu', 'ru')
            if not data:
                await interaction.followup.send("Не удалось получить данные об аффиксах.", ephemeral=True)
                return
            embed = discord.Embed(
                title=data['title'],
                color=discord.Color.blue(),
                description="Аффиксы активны для региона EU"
            )
            for affix in data["affix_details"]:
                ru_name = affix.get("name") or AFFIX_TRANSLATIONS.get(affix.get("name"), affix.get("name"))
                ru_desc = affix.get("description") or ""
                embed.add_field(name=f"{ru_name}", value=ru_desc, inline=False)
            embed.set_footer(text="Источник: Raider.IO | Подробнее: https://ru.wowhead.com/affixes")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(
                f"Произошла ошибка при получении данных: {e}", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))

