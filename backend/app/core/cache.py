"""简单的内存 TTL 缓存，用于减少重复数据库查询和计算。"""

import time
import asyncio
from functools import wraps
from collections import OrderedDict


class TTLCache:
    """带 TTL 的内存缓存在（基于 OrderedDict 实现 LRU 淘汰）。"""

    def __init__(self, maxsize: int = 128, ttl: float = 300.0):
        self._cache: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl  # 秒
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> object | None:
        async with self._lock:
            if key not in self._cache:
                return None
            expires_at, value = self._cache[key]
            if time.monotonic() > expires_at:
                del self._cache[key]
                return None
            # LRU: 移到末尾
            self._cache.move_to_end(key)
            return value

    async def set(self, key: str, value: object, ttl: float | None = None) -> None:
        async with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                while len(self._cache) >= self._maxsize:
                    self._cache.popitem(last=False)
            self._cache[key] = (time.monotonic() + (ttl or self._ttl), value)

    async def invalidate(self, prefix: str | None = None) -> int:
        """失效匹配前缀的缓存键，返回清除的条目数。"""
        async with self._lock:
            if prefix is None:
                count = len(self._cache)
                self._cache.clear()
                return count
            keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._cache[k]
            return len(keys_to_delete)


# ── 全局缓存实例 ──
risk_scan_cache = TTLCache(maxsize=64, ttl=600)  # 风险扫描结果缓存10分钟
profile_cache = TTLCache(maxsize=64, ttl=600)


def cached(cache: TTLCache, key_prefix: str):
    """装饰器：为异步函数添加缓存。缓存键 = key_prefix + ":" + 参数的 "#" .join(str(a) for a in args)。"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = f"{key_prefix}:{'#'.join(str(a) for a in args)}"
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            result = await func(*args, **kwargs)
            await cache.set(cache_key, result)
            return result
        return wrapper
    return decorator


def invalidate_enterprise_caches(enterprise_id: str):
    """企业数据变更时，清除该企业的所有缓存。"""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(risk_scan_cache.invalidate(enterprise_id))
        loop.create_task(profile_cache.invalidate(enterprise_id))
    except RuntimeError:
        pass
