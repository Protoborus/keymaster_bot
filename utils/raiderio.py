import aiohttp
import logging
import asyncio
import random
from typing import Optional

# Семафор для ограничения параллельных запросов к Raider.IO
RAIDEROIO_SEMAPHORE = asyncio.Semaphore(5)

# Параметры retry
MAX_RETRIES = 3
BASE_DELAY = 0.8  # seconds
MAX_DELAY = 8.0


async def _request_with_retry(url: str, params: dict | None = None) -> Optional[dict]:
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with RAIDEROIO_SEMAPHORE:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status in (400, 404):
                            # 400 Bad Request or 404 Not Found - treat as no data for this character
                            try:
                                text = await response.text()
                            except Exception:
                                text = '<no body>'
                            # Log minimal info for diagnostics and do not raise for 400/404
                            logging.getLogger(__name__).warning(
                                "Raider.IO returned %s for %s (params=%s) - body=%s",
                                response.status, url, params, (text[:300] if isinstance(text, str) else str(text))
                            )
                            return None
                        elif response.status == 429 or 500 <= response.status < 600:
                            # transient error, will retry
                            last_exc = aiohttp.ClientResponseError(
                                request_info=response.request_info,
                                history=response.history,
                                status=response.status,
                                message=await response.text(),
                            )
                        else:
                            response.raise_for_status()
        except Exception as e:
            last_exc = e

        # backoff with jitter
        if attempt < MAX_RETRIES:
            backoff = min(MAX_DELAY, BASE_DELAY * (2 ** (attempt - 1)))
            jitter = random.uniform(0, backoff * 0.2)
            await asyncio.sleep(backoff + jitter)

    # If we exit loop without returning, raise last exception
    if last_exc:
        raise last_exc
    return None


async def get_character_data(name: str, realm: str, region: str) -> Optional[dict]:
    url = "https://raider.io/api/v1/characters/profile"
    params = {
        "region": region,
        "realm": realm,
        "name": name,
        "fields": "gear,guild,mythic_plus_scores_by_season:current,mythic_plus_best_runs,mythic_plus_weekly_highest_level_runs"
    }

    return await _request_with_retry(url, params=params)


async def get_weekly_affixes(region: str = 'eu', locale: str = 'en') -> Optional[dict]:
    url = f"https://raider.io/api/v1/mythic-plus/affixes"
    params = {"region": region, "locale": locale}
    return await _request_with_retry(url, params=params)