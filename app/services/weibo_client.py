import json
import random
import time
from typing import Any, Dict, List, Optional

import urllib3
from loguru import logger

from app.config.weibo import WeiboSettings, get_settings
from app.models.weibo import WeiboPic, WeiboPost, WeiboUser
from app.utils.text import build_large_image_url, strip_html


class WeiboHTTPError(Exception):
    pass


class WeiboClient:
    """Lightweight client for m.weibo.cn mobile API using urllib3.

    This avoids bringing extra deps while supporting proxy, retries, and basic anti-bot handling.
    """

    BASE = "https://m.weibo.cn/api"

    def __init__(
        self,
        settings: Optional[WeiboSettings] = None,
        use_proxy: bool = False,
        http: Optional[Any] = None,
    ):
        self.settings = settings or get_settings()
        self.use_proxy = use_proxy
        self._http = http  # allow injection for tests
        self._init_http_pool()

    def _init_http_pool(self):
        if self._http:
            return
        timeout = urllib3.Timeout(connect=self.settings.timeout_s, read=self.settings.timeout_s)
        if self.use_proxy and self.settings.proxy:
            self._http = urllib3.ProxyManager(self.settings.proxy, timeout=timeout, retries=False)
        else:
            self._http = urllib3.PoolManager(timeout=timeout, retries=False)

    def _headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        hdrs = {
            "User-Agent": self.settings.ua,
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
        }
        if self.settings.cookie:
            hdrs["Cookie"] = self.settings.cookie
        if referer:
            hdrs["Referer"] = referer
        return hdrs

    def _request_json(self, path: str, params: Dict[str, Any], referer: Optional[str] = None) -> Dict[str, Any]:
        if not self.settings.cookie:
            raise WeiboHTTPError("WEIBO_COOKIE is not set. Please set a valid cookie from m.weibo.cn")

        from urllib.parse import urlencode

        url = f"{self.BASE}{path}"
        encoded_params = urlencode(params)
        full_url = f"{url}?{encoded_params}" if params else url

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.settings.max_retries + 1):
            try:
                resp = self._http.request(
                    "GET",
                    full_url,
                    headers=self._headers(referer=referer),
                )
                status = getattr(resp, "status", 0)
                body = resp.data.decode("utf-8") if hasattr(resp, "data") else "{}"
                if status in (403, 418, 429):
                    msg = f"Weibo API blocked the request with status {status}. Check cookie/proxy/UA."
                    raise WeiboHTTPError(msg)
                if status >= 500:
                    raise WeiboHTTPError(f"Server error {status}")

                data = json.loads(body)
                if not data:
                    raise WeiboHTTPError("Empty response from Weibo API")
                return data
            except Exception as e:
                last_exc = e
                base = min(5.0, 0.5 * attempt)
                jitter = random.uniform(0, 0.5)
                sleep_s = base + jitter
                logger.warning(f"Weibo request failed (attempt {attempt}/{self.settings.max_retries}): {e}. Sleep {sleep_s:.2f}s")
                time.sleep(sleep_s)
        # max retries exhausted
        raise WeiboHTTPError(str(last_exc) if last_exc else "Unknown request error")

    def get_user_containerid(self, uid: str) -> str:
        """Resolve the containerid for user's weibo tab by uid.
        The API: /container/getIndex?type=uid&value={uid}
        """
        data = self._request_json(
            "/container/getIndex",
            {"type": "uid", "value": uid, "uid": uid},
            referer=f"https://m.weibo.cn/u/{uid}",
        )
        if not data or data.get("ok") != 1:
            raise WeiboHTTPError("Failed to resolve user containerid")
        tabs = (
            data.get("data", {})
            .get("tabsInfo", {})
            .get("tabs", [])
        )
        for t in tabs:
            if t.get("tab_type") == "weibo":
                cid = t.get("containerid")
                if cid:
                    return cid
        raise WeiboHTTPError("Weibo tab containerid not found for user")

    def fetch_user_page(self, containerid: str, since_id: Optional[str] = None) -> Dict[str, Any]:
        params = {"containerid": containerid}
        if since_id:
            params["since_id"] = since_id
        return self._request_json(
            "/container/getIndex",
            params,
            referer=f"https://m.weibo.cn/p/index?containerid={containerid}",
        )

    def normalize_cards(self, cards: List[Dict[str, Any]]) -> List[WeiboPost]:
        posts: List[WeiboPost] = []
        for card in cards:
            if card.get("card_type") != 9:  # 9 is mblog
                continue
            mblog = card.get("mblog", {})
            text_html = mblog.get("text", "")
            clean = strip_html(text_html)
            user = mblog.get("user", {})
            user_obj = WeiboUser(
                id=user.get("id"),
                screen_name=user.get("screen_name"),
                gender=user.get("gender"),
                verified=user.get("verified"),
                followers_count=user.get("followers_count"),
            ) if user else None

            pics_meta = mblog.get("pics", []) or []
            pics = []
            for p in pics_meta:
                pics.append(WeiboPic(pid=p.get("pid"), large_url=build_large_image_url(p)))

            post = WeiboPost(
                id=mblog.get("id"),
                mid=mblog.get("mid"),
                mblogid=mblog.get("mblogid"),
                created_at=mblog.get("created_at"),
                text=clean,
                raw_text=mblog.get("raw_text") or clean,
                user=user_obj,
                pics=pics or None,
                region_name=mblog.get("region_name"),
                reposts_count=mblog.get("reposts_count", 0),
                comments_count=mblog.get("comments_count", 0),
                attitudes_count=mblog.get("attitudes_count", 0),
                isLongText=mblog.get("isLongText"),
                topic_id=(mblog.get("topic_id") or None),
                card_meta={
                    "scheme": card.get("scheme"),
                    "itemid": card.get("itemid"),
                },
            )
            posts.append(post)
        return posts
