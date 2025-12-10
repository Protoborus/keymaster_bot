import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List
import asyncio
import logging
import json
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
class RoleButton(discord.ui.Button):
    def __init__(self, role: str, style: discord.ButtonStyle, custom_id: str):
        super().__init__(label=role, style=style, custom_id=custom_id)
        self.role = role

    async def callback(self, interaction: discord.Interaction):
        # Delegate handling to parent view
        view: KeyView = self.view  # type: ignore
        if self.role == 'Танк':
            await view.handle_tank(interaction)
        elif self.role == 'Хил':
            await view.handle_healer(interaction)
        elif self.role == 'ДД':
            await view.handle_dps(interaction)

        # После изменения слотов обновляем embed и состояние кнопок и редактируем сообщение
        try:
            new_embed = await view.update_embed()
            await view.update_buttons(interaction, new_embed)
            # Обновляем сообщение
            try:
                await interaction.response.edit_message(embed=new_embed, view=view)
            except Exception:
                # Иногда response может быть уже выполнен (ephemeral), в таком случае используем followup
                try:
                    await interaction.followup.edit_message(interaction.message.id, embed=new_embed, view=view)  # type: ignore
                except Exception:
                    # последний шанс: fetch original response and edit
                    try:
                        orig = await interaction.original_response()
                        await orig.edit(embed=new_embed, view=view)
                    except Exception:
                        logging.getLogger(__name__).exception("Failed to edit LFG message after role change")
        except Exception:
            logging.getLogger(__name__).exception("Failed to update embed/buttons after role change")


class PersistentRoleButton(discord.ui.Button):
    def __init__(self, role: str, style: discord.ButtonStyle, custom_id: str, delegate_role: str):
        super().__init__(label=role, style=style, custom_id=custom_id)
        self.delegate_role = delegate_role

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        # delegate to view's _delegate method if available
        if hasattr(view, '_delegate'):
            await view._delegate(interaction, self.delegate_role)
        else:
            # fallback: try to find cog and call handler
            try:
                cog = getattr(view, 'cog', None)
                if cog:
                    await cog._handle_persistent_interaction(view.message_id, self.delegate_role, interaction)
            except Exception:
                logging.getLogger(__name__).exception('Failed to delegate persistent role button')


class KeyView(discord.ui.View):
    def __init__(self, bot, author_id, embed_template: Optional[discord.Embed] = None, message_id: int | None = None, tank: int | None = None, healer: int | None = None, dps: list | None = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.author_id = author_id
        self.message_id = message_id

        # Состояние: храним id пользователей
        self.tank: Optional[int] = None
        self.healer: Optional[int] = None
        self.dps: List[int] = []

        # Шаблонный embed для обновления (копируем чтобы избежать мутаций извне)
        self.embed_template = embed_template.copy() if embed_template else None
        # Флаг, что группа уже была объявлена собранной
        self.full_announced = False
        # Восстановление слотов из переданных аргументов
        self.tank: Optional[int] = tank
        self.healer: Optional[int] = healer
        self.dps: List[int] = dps or []

        # Создаём персистентные кнопки с custom_id, зависящим от message_id
        mid = str(self.message_id) if self.message_id else 'tmp'
        self.add_item(RoleButton('Танк', discord.ButtonStyle.primary, custom_id=f"lfg:{mid}:tank"))
        self.add_item(RoleButton('Хил', discord.ButtonStyle.success, custom_id=f"lfg:{mid}:healer"))
        self.add_item(RoleButton('ДД', discord.ButtonStyle.danger, custom_id=f"lfg:{mid}:dps"))
        self.add_item(CloseLFGButton(self.author_id))


class CloseLFGButton(discord.ui.Button):
    def __init__(self, author_id):
        super().__init__(label="⛔ Закрыть", style=discord.ButtonStyle.red, custom_id="close_lfg")
        self.author_id = author_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Только лидер группы может отменить сбор.", ephemeral=True)
            return
        try:
            await interaction.message.delete()
        except Exception:
            pass
        self.view.stop()
        await interaction.response.send_message("Сбор отменен.", ephemeral=True)

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

    async def handle_tank(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        # Toggle off
        if self.tank == user_id:
            self.tank = None
            await self._persist_slots()
            return

        if self.tank is not None and self.tank != user_id:
            await interaction.response.send_message("Слот уже занят", ephemeral=True)
            return

        self._remove_user_from_all(user_id)
        self.tank = user_id
        await self._persist_slots()

    async def handle_healer(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if self.healer == user_id:
            self.healer = None
            await self._persist_slots()
            return

        if self.healer is not None and self.healer != user_id:
            await interaction.response.send_message("Слот уже занят", ephemeral=True)
            return

        self._remove_user_from_all(user_id)
        self.healer = user_id
        await self._persist_slots()

    async def handle_dps(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id in self.dps:
            self.dps = [uid for uid in self.dps if uid != user_id]
            await self._persist_slots()
            return

        if len(self.dps) >= 3:
            await interaction.response.send_message("Слот уже занят", ephemeral=True)
            return

        self._remove_user_from_all(user_id)
        self.dps.append(user_id)
        await self._persist_slots()

    async def _persist_slots(self):
        # Обновляем запись в БД, если message_id известен
        try:
            if self.message_id and hasattr(self.bot, 'db') and self.bot.db:
                await self.bot.db.update_lfg_slots(self.message_id, self.tank, self.healer, self.dps)
        except Exception:
            logging.getLogger(__name__).exception("Failed to persist LFG slots")

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

    # Удалены декораторы @discord.ui.button и связанные методы, чтобы persistent view не содержала динамически созданных discord.ui.Button без custom_id.


class Keys(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Восстанавливаем персистентные LFG view'ы после старта
        try:
            self.bot.loop.create_task(self._restore_views())
        except Exception:
            pass

    async def _restore_views(self):
        await self.bot.wait_until_ready()
        # Загрузим все активные LFG из базы и восстановим view'ы
        try:
            rows = await self.bot.db.get_active_lfgs()
            for row in rows:
                message_id, channel_id, author_id, tank, healer, dps, embed_dict = row
                # Попытка получить оригинальное сообщение, чтобы восстановить embed шаблон
                embed = None
                try:
                    ch = self.bot.get_channel(channel_id)
                    if ch:
                        try:
                            msg = await ch.fetch_message(message_id)
                            embed = msg.embeds[0] if msg.embeds else None
                        except Exception:
                            embed = None
                except Exception:
                    embed = None

                # Если не удалось получить embed из сообщения, попробуем восстановить из сохранённого JSON
                if embed is None and embed_dict:
                    try:
                        embed = discord.Embed.from_dict(embed_dict)
                    except Exception:
                        embed = None

                # При восстановлении регистрируем персистентную версию только с нашим LFG custom_id
                persistent_view = KeyView(self.bot, author_id, embed, message_id=message_id, tank=tank, healer=healer, dps=dps)
                # Оставляем только элементы с custom_id и начинающиеся с "lfg:"
                persistent_view.children[:] = [
                    c for c in persistent_view.children
                    if isinstance(c, discord.ui.Button)
                    and getattr(c, 'custom_id', None)
                    and str(getattr(c, 'custom_id')).startswith('lfg:')
                ]
                try:
                    try:
                        self.bot.add_view(persistent_view, message_id=message_id)
                    except Exception:
                        await self.bot.add_view(persistent_view, message_id=message_id)  # type: ignore
                except Exception:
                    logging.getLogger(__name__).exception("Failed to restore view for message %s", message_id)
        except Exception:
            logging.getLogger(__name__).exception("Error restoring LFG views on startup")

    async def dungeon_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        # DUNGEONS — словарь: ключ — английское, значение — русское
        return [
            app_commands.Choice(name=ru, value=en)
            for en, ru in DUNGEONS.items() if current.lower() in ru.lower() or current.lower() in en.lower()
        ][:25]

    @app_commands.command(name="lfg", description="Найти группу для ключа")
    @app_commands.describe(dungeon="Выберите подземелье", level="Уровень ключа", note="Ваше примечание или пожелание")
    @app_commands.autocomplete(dungeon=dungeon_autocomplete)
    async def lfg(self, interaction: discord.Interaction, dungeon: str, level: int, note: str = ""):
        # Проверка регистрации лидера
        if not await self.bot.db.get_user(interaction.user.id):
            await interaction.response.send_message("Сначала зарегистрируйтесь через `/register`!", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🔥 Сбор: +{level} {dungeon}",
            description=f"👑 **Лидер:** {interaction.user.mention}\n📝 **Инфо:** {note if note.strip() else 'Нет примечания'}",
            color=discord.Color.gold()
        )
        
        # Создаем поля с иконками в заголовках
        embed.add_field(name=f"{ROLE_ICONS['Tank']} Танк", value="Пусто", inline=True)
        embed.add_field(name=f"{ROLE_ICONS['Healer']} Лекарь", value="Пусто", inline=True)
        embed.add_field(name=f"{ROLE_ICONS['DPS']} Бойцы", value="Пусто", inline=True)

        # Отправляем сообщение, затем создаём view с known message_id для persist
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()

        # Сохраняем LFG в БД
        try:
            try:
                embed_json = None
                try:
                    embed_json = json.dumps(embed.to_dict())
                except Exception:
                    embed_json = None
                await self.bot.db.save_lfg(msg.id, interaction.channel.id, interaction.user.id, None, None, [], embed_json)
            except Exception:
                # fallback: save without embed
                await self.bot.db.save_lfg(msg.id, interaction.channel.id, interaction.user.id, None, None, [], None)
        except Exception:
            logging.getLogger(__name__).exception("Failed to save LFG to DB")

        # Создаем view с message_id и прикрепляем её к сообщению для немедленного взаимодействия
        view = KeyView(interaction.client, interaction.user.id, embed, message_id=msg.id)
        try:
            await msg.edit(view=view)
        except Exception:
            # если не удалось прикрепить сразу — не критично
            logging.getLogger(__name__).debug("Не удалось прикрепить view к сообщению сразу")

        # Регистрируем персистентную view — оставляем только наши LFG custom_id элементы
        persistent_view = KeyView(interaction.client, interaction.user.id, embed, message_id=msg.id, tank=view.tank, healer=view.healer, dps=view.dps)
        persistent_view.children[:] = [c for c in persistent_view.children if getattr(c, 'custom_id', None) and str(getattr(c, 'custom_id')).startswith('lfg:')]
        try:
            try:
                self.bot.add_view(persistent_view, message_id=msg.id)
            except Exception:
                await self.bot.add_view(persistent_view, message_id=msg.id)  # type: ignore
        except Exception:
            logging.getLogger(__name__).exception("Failed to add persistent view")

async def setup(bot):
    await bot.add_cog(Keys(bot))