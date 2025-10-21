import json
import os
import time
from typing import Optional, Set

from loguru import logger

from app.config.weibo import get_settings
from app.models import const
from app.models.weibo import CrawlRequest, CrawlResult, CrawlStats, WeiboPost
from app.services.weibo_client import WeiboClient, WeiboHTTPError
from app.utils import utils


class WeiboCrawlerService:
    """Crawl a user's Weibo homepage timeline and persist to JSONL storage."""

    def __init__(self, use_proxy: bool = False):
        self.settings = get_settings()
        self.client = WeiboClient(self.settings, use_proxy=use_proxy)

    @staticmethod
    def storage_dir(uid: Optional[str] = None) -> str:
        root = os.path.join(utils.root_dir(), "data", "weibo", "users")
        if not os.path.exists(root):
            os.makedirs(root, exist_ok=True)
        return root

    @classmethod
    def jsonl_path(cls, uid: str) -> str:
        return os.path.join(cls.storage_dir(), f"{uid}.jsonl")

    @classmethod
    def seen_path(cls, uid: str) -> str:
        return os.path.join(cls.storage_dir(), f"{uid}.seen")

    def load_seen(self, uid: str) -> Set[str]:
        path = self.seen_path(uid)
        seen: Set[str] = set()
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fp:
                    for line in fp:
                        val = line.strip()
                        if val:
                            seen.add(val)
            except Exception as e:
                logger.warning(f"Failed to read seen file: {e}")
        else:
            # also read from jsonl to initialize
            jsonl = self.jsonl_path(uid)
            if os.path.isfile(jsonl):
                try:
                    with open(jsonl, "r", encoding="utf-8") as fp:
                        for line in fp:
                            try:
                                obj = json.loads(line)
                                pid = str(obj.get("id")) if obj.get("id") is not None else None
                                if pid:
                                    seen.add(pid)
                            except Exception:
                                continue
                except Exception as e:
                    logger.warning(f"Failed to scan jsonl for seen init: {e}")
        return seen

    def persist_seen(self, uid: str, seen: Set[str]):
        with open(self.seen_path(uid), "w", encoding="utf-8") as fp:
            for s in sorted(seen):
                fp.write(f"{s}\n")

    def append_posts(self, uid: str, posts: list[WeiboPost]) -> int:
        jsonl = self.jsonl_path(uid)
        count = 0
        with open(jsonl, "a", encoding="utf-8") as fp:
            for p in posts:
                fp.write(p.model_dump_json(ensure_ascii=False) + "\n")
                count += 1
        return count

    def crawl_user(
        self,
        uid: str,
        max_pages: Optional[int] = None,
        delay_s: float = 1.0,
        task_id: Optional[str] = None,
    ) -> CrawlResult:
        max_pages = max_pages or self.settings.default_max_pages
        containerid = self.client.get_user_containerid(uid)
        since_id: Optional[str] = None
        first_since_id: Optional[str] = None
        last_since_id: Optional[str] = None

        stats = CrawlStats(pages=0, fetched=0, written=0)
        seen = self.load_seen(uid)
        logger.info(f"Loaded {len(seen)} seen ids for uid {uid}")

        for page in range(max_pages):
            data = self.client.fetch_user_page(containerid, since_id=since_id)
            if not data or data.get("ok") != 1:
                logger.warning("No more data or request failed.")
                break

            cards = data.get("data", {}).get("cards", [])
            posts = self.client.normalize_cards(cards)
            stats.pages += 1
            stats.fetched += len(posts)

            # Dedupe by id
            new_posts: list[WeiboPost] = []
            for p in posts:
                pid = str(p.id) if p.id is not None else None
                if pid and pid not in seen:
                    seen.add(pid)
                    new_posts.append(p)

            if new_posts:
                added = self.append_posts(uid, new_posts)
                stats.written += added
                logger.info(f"Page {page+1}: appended {added} new posts for {uid}")

            cardlist = data.get("data", {}).get("cardlistInfo", {})
            cur_since_id = str(cardlist.get("since_id")) if cardlist.get("since_id") else None
            if first_since_id is None:
                first_since_id = cur_since_id
            last_since_id = cur_since_id

            if not cur_since_id:
                break

            # rate limiting
            time.sleep(max(0.0, float(delay_s)))
            since_id = cur_since_id

        # persist seen
        self.persist_seen(uid, seen)

        return CrawlResult(
            uid=uid,
            containerid=containerid,
            first_since_id=first_since_id,
            last_since_id=last_since_id,
            stats=stats,
            output_file=self.jsonl_path(uid),
            seen_file=self.seen_path(uid),
        )


def run_crawl_task(task_id: str, body: CrawlRequest):
    from app.services import state as sm

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=5)
    try:
        service = WeiboCrawlerService(use_proxy=bool(body.use_proxy))
        result = service.crawl_user(
            uid=body.uid,
            max_pages=body.max_pages,
            delay_s=body.delay_s or 1.0,
            task_id=task_id,
        )
        logger.success(
            f"Crawl finished for uid={body.uid}, pages={result.stats.pages}, new={result.stats.written}"
        )
        sm.state.update_task(
            task_id,
            state=const.TASK_STATE_COMPLETE,
            progress=100,
            **{
                "uid": body.uid,
                "containerid": result.containerid,
                "stats": result.stats.model_dump(),
                "output_file": result.output_file,
                "seen_file": result.seen_file,
                "first_since_id": result.first_since_id,
                "last_since_id": result.last_since_id,
            },
        )
    except WeiboHTTPError as e:
        logger.error(f"Crawl failed: {e}")
        sm.state.update_task(
            task_id,
            state=const.TASK_STATE_FAILED,
            progress=100,
            **{"error": str(e)},
        )
    except Exception as e:
        logger.exception(e)
        sm.state.update_task(
            task_id,
            state=const.TASK_STATE_FAILED,
            progress=100,
            **{"error": f"unexpected error: {e}"},
        )
