import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List
import asyncio
import logging
from utils.raiderio import get_character_data
from utils.cache import cache
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

# Список подземелий (ключ - английское, значение - русское)
DUNGEONS = {
    "Ara-Kara, City of Echoes": "Ара-Кара, Город Отголосков",
    "Priory of the Sacred Flame": "Приорат Священного Пламени",
    "The Dawnbreaker": "Сияющий Рассвет",
    "Halls of Atonement": "Чертоги Покаяния",
    "Tazavesh, the Veiled Market: Streets of Wonder": "Тайный рынок Тазавеш: Улицы чудес",
    "Tazavesh, the Veiled Market: So'leah's Gambit": "Тайный рынок Тазавеш: Гамбит Со'леи",
    "Operation: Floodgate": "Операция «Шлюз»",
    "Eco-Dome Al'dani": "Заповедник «Аль'дани»",
}

DUNGEON_CHOICES = [
    {"name": "Ара-Кара, Город Отголосков", "value": "Ara-Kara, City of Echoes"},
    {"name": "Приорат Священного Пламени", "value": "Priory of the Sacred Flame"},
    {"name": "Сияющий Рассвет", "value": "The Dawnbreaker"},
    {"name": "Чертоги Покаяния", "value": "Halls of Atonement"},
    {"name": "Тайный рынок Тазавеш: Улицы чудес", "value": "Tazavesh, the Veiled Market: Streets of Wonder"},
    {"name": "Тайный рынок Тазавеш: Гамбит Со'леи", "value": "Tazavesh, the Veiled Market: So'leah's Gambit"},
    {"name": "Операция «Шлюз»", "value": "Operation: Floodgate"},
    {"name": "Заповедник «Аль'дани»", "value": "Eco-Dome Al'dani"},
]
class KeyView(discord.ui.View):
    def __init__(self, bot, author_id, embed_template: Optional[discord.Embed] = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.author_id = author_id

        # Состояние: храним id пользователей
        self.tank: Optional[int] = None
        self.healer: Optional[int] = None
        self.dps: List[int] = []

        # Шаблонный embed для обновления (копируем чтобы избежать мутаций извне)
        self.embed_template = embed_template.copy() if embed_template else None
        # Флаг, что группа уже была объявлена собранной
        self.full_announced = False

    def _remove_user_from_all(self, user_id: int):
        if self.tank == user_id:
            self.tank = None
        if self.healer == user_id:
            self.healer = None
        self.dps = [uid for uid in self.dps if uid != user_id]

    def _format_mentions(self, uids: List[int]) -> str:
        if not uids:
            return "Пусто"
        return ", ".join(f"<@{uid}>" for uid in uids)

    async def _fetch_stats_for(self, user_id: int) -> tuple[Optional[float], Optional[int]]:
        """Возвращает (rio_score, item_level) для пользователя по discord_id.
        Сначала пытается взять из in-memory кэша, затем из базы; если в базе есть запись,
        создаёт асинхронную задачу для обновления кэша через Raider.IO (fire-and-forget).
        """
        try:
            # 1) Попытка взять из кэша
            cached = await cache.get(user_id)
            if cached:
                return cached  # ожидаемый формат (rio, ilvl)

            # 2) Попытка получить из локальной БД
            user_row = None
            if hasattr(self.bot, 'db') and self.bot.db:
                try:
                    user_row = await self.bot.db.get_user(user_id)
                except Exception as e:
                    logging.getLogger(__name__).exception(f"DB error fetching user {user_id}: {e}")

            rio = None
            item_level = None

            if user_row:
                # user_row: (discord_id, character_name, realm_slug, region, rio_score, character_class, thumbnail_url[, item_level])
                try:
                    # Use index access to be resilient to schema changes
                    character_name = user_row[1]
                    realm_slug = user_row[2]
                    region = user_row[3]
                    rio_score = user_row[4]
                    # optional item_level at index 7
                    item_level = user_row[7] if len(user_row) > 7 else None
                    rio = rio_score
                except Exception:
                    rio = None

                # Запускаем фоновую задачу для обновления кэша и БД, но не ждём её
                try:
                    asyncio.create_task(self._refresh_and_update_cache(user_id, character_name, realm_slug, region))
                except Exception:
                    logging.getLogger(__name__).debug("Не удалось создать задачу обновления кэша")

            return rio, item_level
        except Exception:
            logging.getLogger(__name__).exception(f"Unexpected error fetching stats for user {user_id}")
            return None, None

    async def _refresh_and_update_cache(self, user_id: int, character_name: str, realm_slug: str, region: str, ttl: int = 300):
        """Обновляет данные пользователя: делает запрос к Raider.IO и размещает результат в кэше.
        Также обновляет запись в БД (register_user) при успешном получении данных.
        """
        try:
            # Сетевой запрос с таймаутом
            coro = get_character_data(character_name, realm_slug, region)
            data = await asyncio.wait_for(coro, timeout=8)
            if not data:
                return

            new_score = data.get("mythic_plus_scores_by_season", [{}])[0].get("scores", {}).get("all")
            new_item_level = data.get('gear', {}).get('item_level_equipped')
            new_class = data.get('class')
            new_thumbnail = data.get('thumbnail_url')

            # Сохраняем в кэш
            try:
                await cache.set(user_id, (new_score, new_item_level), ttl=ttl)
            except Exception:
                logging.getLogger(__name__).debug(f"Failed to set cache for {user_id}")

            # Обновляем БД (если доступна)
            if hasattr(self.bot, 'db') and self.bot.db and new_score is not None:
                try:
                    await self.bot.db.register_user(user_id, character_name, realm_slug, region, new_score, new_class, new_thumbnail, new_item_level)
                except Exception:
                    logging.getLogger(__name__).exception(f"Failed to update DB for {character_name}")

        except asyncio.TimeoutError:
            logging.getLogger(__name__).warning(f"Timeout refreshing Raider.IO for {character_name} ({realm_slug})")
        except Exception:
            logging.getLogger(__name__).exception(f"Error refreshing Raider.IO for {character_name} ({realm_slug})")

    async def update_buttons(self, interaction: discord.Interaction, embed: discord.Embed):
        """Обновляет состояние кнопок (disabled) в зависимости от заполненности слотов.
        Если группа полностью собрана (1 танк, 1 хил, 3 дд) — меняет цвет embed на зелёный,
        блокирует кнопки записи и отправляет сообщение о собранной группе в канал (один раз).
        """
        # Определяем состояния
        tank_taken = self.tank is not None
        healer_taken = self.healer is not None
        dps_count = len(self.dps)

        # Обновляем disabled для кнопок
        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            label = getattr(child, 'label', '')
            if label == 'Танк':
                child.disabled = tank_taken
            elif label == 'Хил':
                child.disabled = healer_taken
            elif label == 'ДД':
                child.disabled = (dps_count >= 3)

        # Проверяем полное собрание
        is_full = tank_taken and healer_taken and (dps_count >= 3)
        if is_full:
            # Изменяем цвет embed на зелёный
            try:
                embed.color = discord.Color(0x00ff00)
            except Exception:
                pass

            # Если ещё не объявляли — отправляем сообщение в канал
            if not self.full_announced:
                tank_mention = f"<@{self.tank}>" if self.tank else ""
                healer_mention = f"<@{self.healer}>" if self.healer else ""
                dps_mentions = " ".join(f"<@{uid}>" for uid in self.dps)
                try:
                    if interaction.channel:
                        await interaction.channel.send(f"Группа собрана! 🚀 {tank_mention} {healer_mention} {dps_mentions}")
                except Exception:
                    logging.getLogger(__name__).exception("Failed to send full party announcement")
                self.full_announced = True
        else:
            # Если группа уже не полная — сбрасываем флаг, чтобы можно было объявить снова
            self.full_announced = False

    async def update_embed(self) -> discord.Embed:
        # Берем шаблонный embed, если он есть, иначе создаем новый
        if self.embed_template:
            new_embed = self.embed_template.copy()
        else:
            new_embed = discord.Embed(title="Сбор", color=discord.Color.gold())

        # Очищаем поля и ставим актуальные
        new_embed.clear_fields()
        # Сбор данных для всех участников параллельно
        all_user_ids: List[int] = []
        if self.tank:
            all_user_ids.append(self.tank)
        if self.healer:
            all_user_ids.append(self.healer)
        all_user_ids.extend(self.dps)

        stats_tasks = {uid: asyncio.create_task(self._fetch_stats_for(uid)) for uid in set(all_user_ids)}
        if stats_tasks:
            await asyncio.gather(*stats_tasks.values())

        def fmt(uid: Optional[int]) -> str:
            if not uid:
                return "Пусто"
            rio, ilvl = (None, None)
            task = stats_tasks.get(uid)
            if task and task.done():
                try:
                    rio, ilvl = task.result()
                except Exception:
                    rio, ilvl = (None, None)

            parts = [f"<@{uid}>"]
            if rio is not None:
                parts.append(f"RIo: {int(rio) if isinstance(rio, (int, float)) else rio}")
            if ilvl is not None:
                parts.append(f"iLvl: {ilvl}")
            return " — ".join(parts)

        tank_field = fmt(self.tank)
        healer_field = fmt(self.healer)

        if self.dps:
            dps_lines = []
            for uid in self.dps:
                dps_lines.append(fmt(uid))
            dps_field = "\n".join(dps_lines)
        else:
            dps_field = "Пусто"

        new_embed.add_field(name=f"{ROLE_ICONS['Tank']} Танк", value=tank_field, inline=True)
        new_embed.add_field(name=f"{ROLE_ICONS['Healer']} Лекарь", value=healer_field, inline=True)
        new_embed.add_field(name=f"{ROLE_ICONS['DPS']} Бойцы", value=dps_field, inline=True)
        return new_embed

    @discord.ui.button(label="Танк", style=discord.ButtonStyle.primary, emoji=ROLE_ICONS["Tank"])
    async def tank_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        # Toggle
        if self.tank == user_id:
            # выходит из слота
            self.tank = None
            # сбрасываем объявление полного состава
            self.full_announced = False
        else:
            # если слот уже занят другим — уведомляем
            if self.tank is not None and self.tank != user_id:
                await interaction.response.send_message("Слот уже занят", ephemeral=True)
                return
            # убираем из всех ролей и ставим в танк
            self._remove_user_from_all(user_id)
            self.tank = user_id

        new_embed = await self.update_embed()
        await self.update_buttons(interaction, new_embed)
        await interaction.response.edit_message(embed=new_embed, view=self)

    @discord.ui.button(label="Хил", style=discord.ButtonStyle.success, emoji=ROLE_ICONS["Healer"])
    async def healer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if self.healer == user_id:
            # выходит из слота
            self.healer = None
            self.full_announced = False
        else:
            if self.healer is not None and self.healer != user_id:
                await interaction.response.send_message("Слот уже занят", ephemeral=True)
                return
            self._remove_user_from_all(user_id)
            self.healer = user_id

        new_embed = await self.update_embed()
        await self.update_buttons(interaction, new_embed)
        await interaction.response.edit_message(embed=new_embed, view=self)

    @discord.ui.button(label="ДД", style=discord.ButtonStyle.danger, emoji=ROLE_ICONS["DPS"])
    async def dps_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        # Toggle off if already in list
        if user_id in self.dps:
            # выходит из слота
            self.dps = [uid for uid in self.dps if uid != user_id]
            self.full_announced = False
            new_embed = await self.update_embed()
            await self.update_buttons(interaction, new_embed)
            await interaction.response.edit_message(embed=new_embed, view=self)
            return

        # Если слоты ДД заполнены — сообщаем
        if len(self.dps) >= 3:
            await interaction.response.send_message("Слот уже занят", ephemeral=True)
            return

        # Remove from other roles
        self._remove_user_from_all(user_id)
        # Add if slot available
        self.dps.append(user_id)

        new_embed = await self.update_embed()
        await self.update_buttons(interaction, new_embed)
        await interaction.response.edit_message(embed=new_embed, view=self)

    @discord.ui.button(label="Закрыть сбор", style=discord.ButtonStyle.secondary, row=1)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Только лидер может закрыть сбор.", ephemeral=True)
            return

        self.stop()
        await interaction.response.edit_message(content="❌ Сбор закрыт", embed=None, view=None)


class Keys(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def dungeon_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        # DUNGEONS — словарь: ключ — английское, значение — русское
        return [
            app_commands.Choice(name=ru, value=en)
            for en, ru in DUNGEONS.items() if current.lower() in ru.lower() or current.lower() in en.lower()
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

        view = KeyView(interaction.client, interaction.user.id, embed)
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Keys(bot))