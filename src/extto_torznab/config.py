import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str
    upstream_base: str = "https://extto.com"
    min_interval: float = 3.0
    request_timeout: float = 25.0
    health_max_age: float = 900.0
    backoff_initial: float = 9.0
    backoff_cap: float = 120.0
    magnet_cache_ttl: float = 86_400.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_key=os.getenv("API_KEY", ""),
            upstream_base=os.getenv("UPSTREAM_BASE", "https://extto.com").rstrip("/"),
            min_interval=float(os.getenv("MIN_INTERVAL", "3")),
            request_timeout=float(os.getenv("REQUEST_TIMEOUT", "25")),
            health_max_age=float(os.getenv("HEALTH_MAX_AGE", "900")),
            backoff_initial=float(os.getenv("BACKOFF_INITIAL", "9")),
            backoff_cap=float(os.getenv("BACKOFF_CAP", "120")),
            magnet_cache_ttl=float(os.getenv("MAGNET_CACHE_TTL", "86400")),
        )
