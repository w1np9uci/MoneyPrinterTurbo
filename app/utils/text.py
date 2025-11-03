import html
import re
from typing import Optional


TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    if not text:
        return ""
    # Remove HTML tags
    no_tags = TAG_RE.sub("", text)
    # Unescape HTML entities
    return html.unescape(no_tags).strip()


def build_large_image_url(pic: dict) -> Optional[str]:
    # m.weibo.cn pics item: {pid: str, large: {url: str}, url: ..., largest ...}
    if not pic:
        return None
    large = pic.get("large") or {}
    if isinstance(large, dict) and large.get("url"):
        return large.get("url")
    # fallback to url field
    return pic.get("url")
