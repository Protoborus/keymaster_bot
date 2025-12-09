import time
import asyncio
from typing import Any, Optional


class SimpleTTLCache:
    """Простейший in-memory TTL cache.

    Хранит значения в виде {key: (value, expires_at)}.
    Потокобезопасен для записи через asyncio.Lock.
    """

    def __init__(self, default_ttl: int = 300, maxsize: Optional[int] = 10000):
        self._store: dict[Any, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()
        self.default_ttl = default_ttl
        self.maxsize = maxsize

    async def set(self, key: Any, value: Any, ttl: Optional[int] = None) -> None:
        if ttl is None:
            ttl = self.default_ttl
        expires_at = time.monotonic() + ttl
        async with self._lock:
            # Простая эвикция по размеру
            if self.maxsize and len(self._store) >= self.maxsize:
                # удаляем случайный/первый элемент (простая эвикция)
                try:
                    oldest = next(iter(self._store))
                    self._store.pop(oldest, None)
                except StopIteration:
                    pass
            self._store[key] = (value, expires_at)

    async def get(self, key: Any) -> Optional[Any]:
        item = self._store.get(key)
        if not item:
            return None
        value, expires_at = item
        if time.monotonic() >= expires_at:
            # удаляем устаревшую запись
            async with self._lock:
                self._store.pop(key, None)
            return None
        return value

    async def delete(self, key: Any) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()


# Синглтон кэша по умолчанию
cache = SimpleTTLCache()
