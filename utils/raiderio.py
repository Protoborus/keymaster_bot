import aiohttp

async def get_character_data(name: str, realm: str, region: str):
    url = "https://raider.io/api/v1/characters/profile"
    params = {
        "region": region,
        "realm": realm,
        "name": name,
        "fields": "gear,guild,mythic_plus_scores_by_season:current,mythic_plus_best_runs,mythic_plus_weekly_highest_level_runs"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                return None
            else:
                response.raise_for_status()

async def get_weekly_affixes(region='eu', locale='en'):
    url = f"https://raider.io/api/v1/mythic-plus/affixes?region={region}&locale={locale}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                return None
            else:
                response.raise_for_status()