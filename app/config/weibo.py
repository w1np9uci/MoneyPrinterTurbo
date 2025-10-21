import os
from dataclasses import dataclass
from typing import Optional


DEFAULT_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15A372 Safari/604.1"
)


@dataclass
class WeiboSettings:
    """Runtime settings for Weibo crawler loaded from env.

    - WEIBO_COOKIE: Cookie string from an authenticated mobile session.
    - WEIBO_UA: Optional custom user agent.
    - WEIBO_PROXY: Optional HTTP(S) proxy URL, e.g. http://127.0.0.1:7890
    - WEIBO_DEFAULT_MAX_PAGES: Default pagination depth
    - WEIBO_TIMEOUT_S: HTTP timeout in seconds
    - WEIBO_MAX_RETRIES: Max retry attempts on transient failures
    """

    cookie: str
    ua: str = DEFAULT_UA
    proxy: Optional[str] = None
    default_max_pages: int = 5
    timeout_s: float = 15.0
    max_retries: int = 3


def get_settings() -> WeiboSettings:
    return WeiboSettings(
        cookie=os.getenv("WEIBO_COOKIE", ""),
        ua=os.getenv("WEIBO_UA", DEFAULT_UA),
        proxy=os.getenv("WEIBO_PROXY"),
        default_max_pages=int(os.getenv("WEIBO_DEFAULT_MAX_PAGES", "5")),
        timeout_s=float(os.getenv("WEIBO_TIMEOUT_S", "15")),
        max_retries=int(os.getenv("WEIBO_MAX_RETRIES", "3")),
    )
