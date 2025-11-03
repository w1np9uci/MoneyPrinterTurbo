from typing import Any, List, Optional

from pydantic import BaseModel


class WeiboUser(BaseModel):
    id: Optional[int] = None
    screen_name: Optional[str] = None
    gender: Optional[str] = None
    verified: Optional[bool] = None
    followers_count: Optional[int] = None


class WeiboPic(BaseModel):
    pid: Optional[str] = None
    large_url: Optional[str] = None


class WeiboPost(BaseModel):
    id: Optional[int] = None
    mid: Optional[str] = None
    mblogid: Optional[str] = None
    created_at: Optional[str] = None
    text: Optional[str] = None
    raw_text: Optional[str] = None
    user: Optional[WeiboUser] = None
    pics: Optional[List[WeiboPic]] = None
    region_name: Optional[str] = None
    reposts_count: Optional[int] = 0
    comments_count: Optional[int] = 0
    attitudes_count: Optional[int] = 0
    isLongText: Optional[bool] = None
    topic_id: Optional[str] = None
    card_meta: Optional[dict] = None


class CrawlRequest(BaseModel):
    uid: str
    max_pages: Optional[int] = None
    delay_s: Optional[float] = 1.0
    use_proxy: Optional[bool] = False


class CrawlStats(BaseModel):
    pages: int = 0
    fetched: int = 0
    written: int = 0


class CrawlResult(BaseModel):
    uid: str
    containerid: Optional[str] = None
    first_since_id: Optional[str] = None
    last_since_id: Optional[str] = None
    stats: CrawlStats
    output_file: Optional[str] = None
    seen_file: Optional[str] = None
