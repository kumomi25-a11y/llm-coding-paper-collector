"""Token bucket rate limiter and retry utilities."""

import time
import logging
from functools import wraps
from typing import Callable

logger = logging.getLogger("paper_collector")


class RateLimiter:
    """Simple token bucket rate limiter."""

    def __init__(self, calls_per_second: float, burst: int = 5):
        self.rate = calls_per_second
        self.burst = burst
        self.tokens = burst
        self.last_refill = time.monotonic()

    def acquire(self):
        """Block until a token is available."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_refill = now

        if self.tokens < 1:
            sleep_time = (1 - self.tokens) / self.rate
            time.sleep(sleep_time)
            self.tokens = 0
        else:
            self.tokens -= 1


def retry_on_429(max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
    """Decorator: retry with exponential backoff on HTTP 429."""

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if "429" in str(e) and attempt < max_retries:
                        logger.warning(f"Rate limited (429), retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        delay = min(delay * 2, max_delay)
                    else:
                        raise
            return None

        return wrapper

    return decorator
