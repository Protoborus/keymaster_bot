import discord
from discord.ext import commands
from discord import app_commands
from utils.raiderio import get_weekly_affixes

# Словарь перевода аффиксов
AFFIX_TRANSLATIONS = {
    # Базовые модификаторы
    "Fortified": "Укрепленный",
    "Tyrannical": "Тиранический",
    "Challenger's Peril": "Риск претендента",
    "Xal'atath's Guile": "Вероломство Ксал'атат",

    # Сезонные модификаторы (Сделки)
    "Xal'atath's Bargain: Ascendant": "Сделка с Ксал'атат: Вознесение",
    "Xal'atath's Bargain: Voidbound": "Сделка с Ксал'атат: Слуга Бездны",
    "Xal'atath's Bargain: Devour": "Сделка с Ксал'атат: Пожирание",
    "Xal'atath's Bargain: Oblivion": "Сделка с Ксал'атат: Забвение",
    "Xal'atath's Bargain: Pulsar": "Сделка с Ксал'атат: Пульсар"
}

class Info(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="affixes", description="Показать аффиксы текущей недели")
    async def affixes(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            data = await get_weekly_affixes('eu')
            if not data:
                await interaction.followup.send("Не удалось получить данные об аффиксах.", ephemeral=True)
                return

            embed = discord.Embed(
                title=data['title'],
                color=discord.Color.blue(),
                description="Аффиксы активны для региона EU"
            )

            for affix in data["affix_details"]:
                affix_name = affix["name"]
                affix_desc = affix["description"]

                # Попытка найти перевод аффикса
                ru_name = AFFIX_TRANSLATIONS.get(affix_name, affix_name)
                ru_desc = affix_desc if ru_name == affix_name else AFFIX_TRANSLATIONS.get(affix_name, affix_desc)

                embed.add_field(name=f"{ru_name} ({affix_name})", value=ru_desc, inline=False)

            embed.set_footer(text="Источник: Raider.IO | Подробнее: https://ru.wowhead.com/affixes")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(
                f"Произошла ошибка при получении данных: {e}", ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))