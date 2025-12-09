import discord
from discord.ext import commands
from discord import app_commands

# --- КОНФИГУРАЦИЯ ИКОНОК ---

# ID взяты с сервера пользователя
ROLE_ICONS = {
    "Tank": "<:tank:1447918344337621002>",
    "Healer": "<:healer:1447918402218885231>",
    "DPS": "<:DPS:1447918367569612871>"
}

CLASS_ICONS = {
    "Death Knight": "<:WoWDeathKnight:1360689050855411947>",
    "Demon Hunter": "<:WoWDemonHunter:1360689025522073920>",
    "Druid": "<:WoWDruid:1360689027358916728>",
    "Evoker": "<:WoWEvoker:1360689029430902814>",
    "Hunter": "<:WoWHunter:1360689031171805236>",
    "Mage": "<:WoWMage:1360689033147060556>",
    "Monk": "<:WoWMonk:1360689034971578600>",
    "Paladin": "<:WoWPaladin:1360689036909613226>",
    "Priest": "<:WoWPriest:1360689039551889518>",
    "Rogue": "<:WoWRogue:1360689042324193321>",
    "Shaman": "<:WoWShaman:1360689044681654333>",
    "Warlock": "<:WpWWarlock:1360689047462215770>",
    "Warrior": "<:WoWWarrior:1360689049421086720>"
}

DUNGEONS = [
    "Ара-Кара", "Город Нитей", "Каменное Подземелье", "Сияющий Рассвет",
    "Туманы Тирна Скитта", "Смертельная Тризна", "Осада Боралуса", "Грим Батол"
]

class KeyView(discord.ui.View):
    def __init__(self, bot, author_id):
        super().__init__(timeout=None) # Кнопки вечные (пока бот не перезагрузится)
        self.bot = bot
        self.author_id = author_id

    async def update_embed(self, interaction: discord.Interaction, role_clicked: str):
        # 1. Проверяем регистрацию
        user_data = await self.bot.db.get_user(interaction.user.id)
        if not user_data:
            await interaction.response.send_message("❌ Вы не зарегистрированы! Используйте `/register`.", ephemeral=True)
            return

        # Распаковываем данные (score, class)
        # Порядок в get_user: id, name, realm, region, score, class, thumbnail
        _, char_name, _, _, rio_score, char_class, _ = user_data

        # 2. Получаем текущий Embed
        msg = interaction.message
        if not msg or not msg.embeds:
            await interaction.response.send_message("Не удалось получить сообщение с Embed. Повторите попытку.", ephemeral=True)
            return
        embed = msg.embeds[0]
        
        # 3. Формируем строку участника
        class_icon = CLASS_ICONS.get(char_class, "❓")
        # Округляем счет до целого
        score_int = int(rio_score) if rio_score else 0
        new_entry = f"{class_icon} **{char_name}** ({score_int})"

        # 4. Логика обновления полей
        # Нам нужно найти поле для нужной роли и добавить туда человека.
        # Если он уже есть в ДРУГОЙ роли — удалить оттуда.
        # Если он уже есть в ЭТОЙ роли — удалить (toggle).

        target_field_index = -1
        role_map = {"Tank": 0, "Healer": 1, "DPS": 2} # Индексы полей в Embed
        target_idx = role_map[role_clicked]

        # Очищаем имя пользователя из всех полей (чтобы не дублировался)
        user_removed = False
        for i, field in enumerate(embed.fields):
            field_value = field.value or "Пусто"
            lines = str(field_value).split('\n')
            # Фильтруем строки, удаляя ту, где есть имя пользователя
            new_lines = [line for line in lines if f"**{char_name}**" not in line and line != "Пусто"]
            
            # Если мы кликнули по этой роли и удалили юзера — значит он хотел выйти (Toggle)
            if i == target_idx and len(lines) != len(new_lines):
                user_removed = True
            
            # Собираем поле обратно
            new_value = "\n".join(new_lines) if new_lines else "Пусто"
            embed.set_field_at(i, name=field.name, value=new_value, inline=True)

        # Если мы не удаляли пользователя (или удалили из другой роли), добавляем в новую
        if not user_removed:
            current_field = embed.fields[target_idx]
            current_val = current_field.value or "Пусто"
            
            if current_val == "Пусто":
                new_val = new_entry
            else:
                new_val = str(current_val) + "\n" + new_entry
            
            embed.set_field_at(target_idx, name=current_field.name, value=new_val, inline=True)

        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Танк", style=discord.ButtonStyle.primary, emoji=ROLE_ICONS["Tank"])
    async def tank_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_embed(interaction, "Tank")

    @discord.ui.button(label="Хил", style=discord.ButtonStyle.success, emoji=ROLE_ICONS["Healer"])
    async def healer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_embed(interaction, "Healer")

    @discord.ui.button(label="ДД", style=discord.ButtonStyle.danger, emoji=ROLE_ICONS["DPS"])
    async def dps_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_embed(interaction, "DPS")

    @discord.ui.button(label="Закрыть сбор", style=discord.ButtonStyle.secondary, row=1)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Только лидер может закрыть сбор.", ephemeral=True)
            return
        msg = interaction.message
        if not msg or not msg.embeds:
            await interaction.response.send_message("Не удалось получить сообщение с Embed.", ephemeral=True)
            return
        embed = msg.embeds[0]
        embed.title = f"❌ Сбор закрыт: {embed.title}"
        embed.color = discord.Color.default()
        await interaction.response.edit_message(embed=embed, view=None)


class Keys(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def dungeon_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=d, value=d)
            for d in DUNGEONS if current.lower() in d.lower()
        ][:25]

    @app_commands.command(name="lfg", description="Найти группу для ключа")
    @app_commands.describe(dungeon="Выберите подземелье", level="Уровень ключа", note="Примечание (БЛ, КР, опыт)")
    @app_commands.autocomplete(dungeon=dungeon_autocomplete)
    async def lfg(self, interaction: discord.Interaction, dungeon: str, level: int, note: str = ""):
        # Проверка регистрации лидера
        if not await self.bot.db.get_user(interaction.user.id):
            await interaction.response.send_message("Сначала зарегистрируйтесь через `/register`!", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🔥 Сбор: +{level} {dungeon}",
            description=f"👑 **Лидер:** {interaction.user.mention}\n📝 **Инфо:** {note if note else 'Нет примечаний'}",
            color=discord.Color.gold()
        )
        
        # Создаем поля с иконками в заголовках
        embed.add_field(name=f"{ROLE_ICONS['Tank']} Танк", value="Пусто", inline=True)
        embed.add_field(name=f"{ROLE_ICONS['Healer']} Лекарь", value="Пусто", inline=True)
        embed.add_field(name=f"{ROLE_ICONS['DPS']} Бойцы", value="Пусто", inline=True)

        view = KeyView(self.bot, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Keys(bot))