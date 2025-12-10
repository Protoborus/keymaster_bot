import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from utils.database import Database
from utils.raiderio import get_character_data
from discord.ext import tasks
import asyncio
import logging
from utils.cache import cache
from typing import Optional

# Логгер модуля
logger = logging.getLogger(__name__)

# Словарь популярных RU/EU серверов
REALMS = {
    "Гордунни": "gordunni",
    "Ревущий фьорд": "howling-fjord",
    "Свежеватель Душ": "soulflayer",
    "Азурегос": "azuregos",
    "Борейская тундра": "borean-tundra",
    "Вечная Песня": "eversong",
    "Галакронд": "galakrond",
    "Голдринн": "goldrinn",
    "Гром": "grom",
    "Король-лич": "lich-king",
    "Пиратская Бухта": "booty-bay",
    "Подземье": "deepholm",
    "Страж Смерти": "deathguard",
    "Термоштепсель": "thermaplugg",
    "Фордрагон": "fordragon",
    "Черный Шрам": "blackscar"
}

# Словарь перевода подземелий
DUNGEON_RU = {
    "Ara-Kara, City of Echoes": "Ара-Кара, Город Отголосков",
    "Priory of the Sacred Flame": "Приорат Священного Пламени",
    "The Dawnbreaker": "Сияющий Рассвет",
    "Halls of Atonement": "Чертоги Покаяния",
    "Tazavesh, the Veiled Market: Streets of Wonder": "Тайный рынок Тазавеш: Улицы чудес",
    "Tazavesh, the Veiled Market: So'leah's Gambit": "Тайный рынок Тазавеш: Гамбит Со'леи",
    "Operation: Floodgate": "Операция «Шлюз»",
    "Eco-Dome Al'dani": "Заповедник «Аль'дани»"
}

# Цвета классов WoW
CLASS_COLORS = {
    "Death Knight": 0xC41E3A, "Demon Hunter": 0xA330C9, "Druid": 0xFF7C0A,
    "Evoker": 0x33937F, "Hunter": 0xAAD372, "Mage": 0x3FC7EB, "Monk": 0x00FF98,
    "Paladin": 0xF48CBA, "Priest": 0xFFFFFF, "Rogue": 0xFFF468,
    "Shaman": 0x0070DE, "Warlock": 0x8788EE, "Warrior": 0xC69B6D
}

class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.background_update.start()

    def cog_unload(self):
        self.background_update.cancel()

    # Функция автодополнения для параметра realm
    async def realm_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        current = current.lower()
        choices = [
            app_commands.Choice(name=name, value=slug)
            for name, slug in REALMS.items()
            if current in name.lower() or current in slug.lower()
        ]
        return choices[:25]  # Лимитируем до 25 результатов

    # Choices for realm and region — force selection to avoid invalid slugs
    REALM_CHOICES = [app_commands.Choice(name=name, value=slug) for name, slug in REALMS.items()]
    REGION_CHOICES = [
        app_commands.Choice(name="EU", value="eu"),
        app_commands.Choice(name="US", value="us"),
        app_commands.Choice(name="KR", value="kr"),
        app_commands.Choice(name="CN", value="cn"),
    ]

    @app_commands.command(name="register", description="Регистрация персонажа Raider.IO")
    @app_commands.choices(region=REGION_CHOICES)
    @app_commands.autocomplete(realm=realm_autocomplete)
    @app_commands.describe(region="Регион персонажа", realm="Сервер персонажа", name="Имя персонажа")
    async def register(self, interaction: discord.Interaction, region: app_commands.Choice[str], realm: str, name: str):
        """Регистрация: region и realm выбираются из списка. Проверяем существование персонажа на Raider.IO
        и только после позитивного ответа сохраняем запись в БД."""
        region_slug = region.value
        realm_slug = realm

        # Проверяем у Raider.IO наличие персонажа
        data = await get_character_data(name, realm_slug, region_slug)
        if not data:
            await interaction.response.send_message(
                f"Ошибка: не удалось найти персонажа '{name}' на сервере '{realm}' ({region.name}). Проверьте корректность данных.",
                ephemeral=True,
            )
            return

        # Разбор данных
        try:
            rio_score = data["mythic_plus_scores_by_season"][0]["scores"]["all"]
        except Exception:
            rio_score = 0

        thumbnail_url = data.get("thumbnail_url")
        main_class = data.get("class")
        item_level = data.get('gear', {}).get('item_level_equipped')

        # Сохраняем в БД
        await Database().register_user(
            interaction.user.id, name, realm_slug, region_slug, rio_score, main_class, thumbnail_url, item_level
        )

        # Обновляем кэш для быстрого отображения
        try:
            await cache.set(interaction.user.id, (rio_score, item_level))
        except Exception:
            logger.debug("Не удалось записать кэш после регистрации")

        embed = discord.Embed(title="Регистрация успешна!", color=discord.Color.green())
        embed.add_field(name="Персонаж", value=f"{name} ({realm}, {region.name})", inline=False)
        embed.add_field(name="Рейтинг", value=f"{rio_score}", inline=True)
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="me", description="Показать информацию о вашем профиле")
    async def profile(self, interaction: discord.Interaction):
        # Получение данных пользователя из базы
        user_data = await Database().get_user(interaction.user.id)

        if user_data:
            # Database schema may include optional `item_level` as the 8th column.
            # Unpack defensively to avoid ValueError if schema changed.
            discord_id, character_name, realm_slug, region, rio_score, char_class, thumbnail, *rest = user_data
            item_level = rest[0] if rest else None

            # Запрос к Raider.IO API
            try:
                data = await get_character_data(character_name, realm_slug, region)
                if not data:
                    await interaction.response.send_message(
                        "Персонаж не найден на Raider.IO. Проверьте данные.", ephemeral=True
                    )
                    return

                embed = self.create_character_embed(data)
                await interaction.response.send_message(embed=embed)

            except Exception as e:
                await interaction.response.send_message(
                    f"Ошибка при получении данных с Raider.IO: {e}", ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "Вы не зарегистрированы. Используйте команду `/register`, чтобы зарегистрироваться.",
                ephemeral=True
            )

    @app_commands.command(name="check", description="Проверить Raider.IO любого персонажа")
    @app_commands.choices(region=REGION_CHOICES)
    @app_commands.autocomplete(realm=realm_autocomplete)
    @app_commands.describe(name="Имя", realm="Сервер", region="Регион")
    async def check(self, interaction: discord.Interaction, name: str, realm: str, region: app_commands.Choice[str]):
        await interaction.response.defer()

        try:
            data = await get_character_data(name, realm, region.value)
            if data is None:
                await interaction.followup.send(
                    f"❌ Персонаж **{name}** ({realm}) не найден. Проверьте правильность ника и сервера.",
                    ephemeral=True
                )
                return

            embed = self.create_character_embed(data)
            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(
                f"Ошибка при получении данных с Raider.IO: {e}", ephemeral=True
            )

    @app_commands.command(name="top", description="Показать топ игроков сервера")
    async def top(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            top_users = await Database().get_top_users(10)
            if not top_users:
                await interaction.followup.send("Топ игроков пуст. Зарегистрируйтесь через /register!", ephemeral=True)
                return

            embed = discord.Embed(title="🏆 Топ игроков сервера", color=discord.Color.gold())

            medals = ["🥇", "🥈", "🥉"]
            for idx, user in enumerate(top_users):
                name, realm, score, char_class = user
                medal = medals[idx] if idx < len(medals) else f"{idx + 1}."
                embed.add_field(
                    name=f"{medal} {char_class} {name}",
                    value=f"Сервер: {realm}, Рейтинг: {score}",
                    inline=False
                )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(
                f"Произошла ошибка при получении топа: {e}", ephemeral=True
            )

    def get_score_emoji(self, score: float) -> str:
        if score < 1500:
            return "🟢"  # Зеленый / Необычный
        elif 1500 <= score < 2000:
            return "🔵"  # Синий / Редкий
        elif 2000 <= score < 2500:
            return "🟣"  # Фиолетовый / Эпический
        else:
            return "🟠"  # Оранжевый / Легендарный

    def create_character_embed(self, data) -> discord.Embed:
        rio_score = data["mythic_plus_scores_by_season"][0]["scores"]["all"]
        item_level = data.get("gear", {}).get("item_level_equipped", 0)
        guild_name = data.get("guild", {}).get("name", "Без гильдии")
        thumbnail_url = data["thumbnail_url"]
        profile_url = data["profile_url"]

        # Формирование списка лучших забегов
        best_runs = data.get("mythic_plus_best_runs", [])
        best_runs = sorted(best_runs, key=lambda x: x["score"], reverse=True)[:5]
        best_runs_text = []
        for run in best_runs:
            dungeon_name = DUNGEON_RU.get(run["dungeon"], run["dungeon"])
            level = run["mythic_level"]
            upgrades = "⭐" * run["num_keystone_upgrades"]
            best_runs_text.append(f"+{level} {dungeon_name} ({upgrades})")

        best_runs_field = "\n".join(best_runs_text) if best_runs_text else "Нет данных о забегах."

        emoji = self.get_score_emoji(rio_score)
        embed = discord.Embed(
            title=f"{data['name']} ({data['class']}) - {guild_name}",
            color=CLASS_COLORS.get(data['class'], 0x808080),
            description=f"[Профиль на Raider.IO]({profile_url})"
        )
        embed.set_thumbnail(url=thumbnail_url)
        embed.add_field(name="Raider.IO Score", value=f"{emoji} **{rio_score}**", inline=True)
        embed.add_field(name="Item Level", value=f"{item_level}", inline=True)
        embed.add_field(name="🏆 Лучшие забеги", value=best_runs_field, inline=False)

        return embed

    @app_commands.command(name="update", description="Обновить данные моего персонажа с Raider.IO")
    async def update(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            user_data = await Database().get_user(interaction.user.id)
            if not user_data:
                await interaction.followup.send("Вы не зарегистрированы. Используйте команду `/register`, чтобы зарегистрироваться.", ephemeral=True)
                return

            discord_id, character_name, realm_slug, region, old_score, char_class, thumbnail, *rest = user_data
            old_item_level = rest[0] if rest else None

            # Запрос к Raider.IO API
            data = await get_character_data(character_name, realm_slug, region)
            if not data:
                await interaction.followup.send(
                    "❌ Не удалось получить данные с Raider.IO. Проверьте настройки персонажа или попробуйте позже.",
                    ephemeral=True
                )
                return

            new_score = data["mythic_plus_scores_by_season"][0]["scores"]["all"]
            new_thumbnail = data["thumbnail_url"]
            new_class = data["class"]

            # Обновление данных в базе
            new_item_level = data.get('gear', {}).get('item_level_equipped')
            await Database().register_user(
                interaction.user.id, character_name, realm_slug, region, new_score, new_class, new_thumbnail, new_item_level
            )

            # Обновить кэш после ручного обновления
            try:
                new_item_level = data.get('gear', {}).get('item_level_equipped')
                await cache.set(interaction.user.id, (new_score, new_item_level))
            except Exception:
                logger.debug("Не удалось записать кэш после /update")

            embed = discord.Embed(title="✅ Профиль обновлен!", color=discord.Color.green())
            embed.add_field(name="Рейтинг", value=f"{old_score} ➡️ {new_score}", inline=False)
            if new_score > old_score:
                embed.add_field(name="Прогресс", value="📈 Поздравляю с прогрессом!", inline=False)

            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(
                f"Произошла ошибка при обновлении данных: {e}", ephemeral=True
            )

    @app_commands.command(name="weekly", description="Показать прогресс недельного хранилища")
    @app_commands.choices(region=REGION_CHOICES)
    @app_commands.autocomplete(realm=realm_autocomplete)
    @app_commands.describe(
        name="Имя персонажа (оставьте пустым для своего профиля)",
        realm="Сервер персонажа (обязательно вместе с именем)",
        region="Регион персонажа (обязательно вместе с именем)",
    )
    async def weekly(
        self,
        interaction: discord.Interaction,
        name: Optional[str] = None,
        realm: Optional[str] = None,
        region: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer()

        try:
            if name:
                if not realm or not region:
                    await interaction.followup.send(
                        "Укажите имя, сервер и регион персонажа, которого хотите проверить.",
                        ephemeral=True,
                    )
                    return

                target_name = name
                target_realm = realm
                target_region = region.value
            else:
                user_data = await self.bot.db.get_user(interaction.user.id)
                if not user_data:
                    await interaction.followup.send(
                        "Вы не зарегистрированы. Используйте команду `/register`, чтобы зарегистрироваться.",
                        ephemeral=True,
                    )
                    return

                _, target_name, target_realm, target_region, *_ = user_data

            data = await get_character_data(target_name, target_realm, target_region)
            if not data:
                await interaction.followup.send(
                    f"❌ Персонаж **{target_name}** на сервере **{target_realm}** не найден.",
                    ephemeral=True,
                )
                return

            weekly_runs = data.get("mythic_plus_weekly_highest_level_runs", [])

            embed = discord.Embed(
                title=f"🎁 Недельный прогресс для {target_name}",
                color=discord.Color.blue()
            )

            if not weekly_runs:
                embed.description = "На этой неделе ключи еще не закрыты."
            else:
                runs_text = []
                for i, run in enumerate(weekly_runs[:8], start=1):
                    dungeon_name = DUNGEON_RU.get(run["dungeon"], run["dungeon"])
                    level = run["mythic_level"]
                    runs_text.append(f"{i}. +{level} {dungeon_name}")

                embed.description = "\n".join(runs_text)
                embed.set_footer(text=f"Закрыто ключей: {len(weekly_runs)}/8")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(
                f"Произошла ошибка при получении данных: {e}", ephemeral=True
            )

    @tasks.loop(hours=1)
    async def background_update(self):
        await self.bot.wait_until_ready()
        logger.info("🔄 Запуск фоновой задачи обновления...")
        try:
            users = await self.bot.db.get_all_users()
            logger.info(f"📊 Найдено пользователей в базе: {len(users)}")
            for user in users:
                discord_id, character_name, realm_slug, region = user
                try:
                    data = await get_character_data(character_name, realm_slug, region)
                    if not data:
                        logger.warning(f"⚠️ Ошибка обновления для {character_name} ({realm_slug}). Пропуск.")
                        continue

                    new_score = data["mythic_plus_scores_by_season"][0]["scores"]["all"]
                    new_thumbnail = data["thumbnail_url"]
                    new_class = data["class"]

                    await self.bot.db.register_user(
                        discord_id, character_name, realm_slug, region, new_score, new_class, new_thumbnail, data.get('gear', {}).get('item_level_equipped')
                    )

                    # Обновляем кэш, если пользователь есть в кэше
                    try:
                        new_item_level = data.get('gear', {}).get('item_level_equipped')
                        await cache.set(discord_id, (new_score, new_item_level))
                    except Exception:
                        logger.debug(f"Не удалось записать кэш для {character_name}")

                    await asyncio.sleep(2)  # Задержка для предотвращения спама API
                except Exception as e:
                    logger.exception(f"Ошибка при обновлении пользователя {character_name}: {e}")
            logger.info(f"🏁 Фоновое обновление завершено. Обработано {len(users)} пользователей.")
        except Exception as e:
            logger.exception(f"Ошибка при выполнении фоновой задачи: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))