import os
import json
from typing import Optional

from fastapi import BackgroundTasks, Query, Request
from loguru import logger

from app.controllers import base
from app.controllers.manager.memory_manager import InMemoryTaskManager
from app.controllers.manager.redis_manager import RedisTaskManager
from app.controllers.v1.base import new_router
from app.models.exception import HttpException
from app.models.schema import TaskResponse
from app.models.weibo import CrawlRequest
from app.services import state as sm
from app.services.weibo_crawler import WeiboCrawlerService, run_crawl_task
from app.utils import utils

router = new_router()

# Task manager config same as video controller
from app.config import config

_enable_redis = config.app.get("enable_redis", False)
_redis_host = config.app.get("redis_host", "localhost")
_redis_port = config.app.get("redis_port", 6379)
_redis_db = config.app.get("redis_db", 0)
_redis_password = config.app.get("redis_password", None)
_max_concurrent_tasks = config.app.get("max_concurrent_tasks", 5)

redis_url = f"redis://:{_redis_password}@{_redis_host}:{_redis_port}/{_redis_db}"
if _enable_redis:
    task_manager = RedisTaskManager(max_concurrent_tasks=_max_concurrent_tasks, redis_url=redis_url)
else:
    task_manager = InMemoryTaskManager(max_concurrent_tasks=_max_concurrent_tasks)


@router.post("/weibo/crawl/user", response_model=TaskResponse, summary="Start crawling a user's Weibo timeline by uid")
def crawl_user(background_tasks: BackgroundTasks, request: Request, body: CrawlRequest):
    task_id = utils.get_uuid()
    request_id = base.get_task_id(request)
    try:
        task = {
            "task_id": task_id,
            "request_id": request_id,
            "params": body.model_dump(),
        }
        sm.state.update_task(task_id)
        task_manager.add_task(run_crawl_task, task_id=task_id, body=body)
        logger.success(f"Weibo crawl task created: {utils.to_json(task)}")
        return utils.get_response(200, task)
    except ValueError as e:
        raise HttpException(task_id=task_id, status_code=400, message=f"{request_id}: {str(e)}")


@router.get("/weibo/posts/user", summary="Read normalized posts from storage with pagination")
def get_user_posts(
    request: Request,
    uid: str = Query(..., description="Weibo user uid"),
    limit: int = Query(20, ge=1, le=200),
    since_id: Optional[str] = Query(None, description="Return items after this post id"),
):
    service = WeiboCrawlerService()
    jsonl = service.jsonl_path(uid)
    if not os.path.isfile(jsonl):
        raise HttpException(task_id=uid, status_code=404, message=f"No posts found for uid={uid}")

    posts = []
    with open(jsonl, "r", encoding="utf-8") as fp:
        for line in fp:
            try:
                posts.append(json.loads(line))
            except Exception:
                continue

    # Find start index by since_id
    start = 0
    if since_id:
        for idx, p in enumerate(posts):
            if str(p.get("id")) == str(since_id):
                start = idx + 1
                break

    slice_ = posts[start:start + limit]
    next_cursor = None
    if slice_:
        next_cursor = str(slice_[-1].get("id")) if slice_[-1].get("id") is not None else None

    return utils.get_response(200, {"posts": slice_, "next_since_id": next_cursor})
