import json
import os
from typing import Dict, Any

import pytest

from app.controllers.v1 import weibo as weibo_controller
from app.services.weibo_crawler import WeiboCrawlerService
from app.services.weibo_client import WeiboClient


@pytest.fixture(autouse=True)
def set_cookie_env(monkeypatch):
    # ensure cookie set so client doesn't fail
    monkeypatch.setenv("WEIBO_COOKIE", "TEST=1;")


def make_container_resp(uid: str, containerid: str) -> Dict[str, Any]:
    return {
        "ok": 1,
        "data": {
            "tabsInfo": {
                "tabs": [
                    {"tab_type": "profile", "containerid": f"230283{uid}"},
                    {"tab_type": "weibo", "containerid": containerid},
                ]
            }
        },
    }


def make_page_resp(ids, since_id=None) -> Dict[str, Any]:
    cards = []
    for i in ids:
        cards.append(
            {
                "card_type": 9,
                "mblog": {
                    "id": int(i),
                    "mid": str(i),
                    "mblogid": f"M{i}",
                    "created_at": "Tue Jan 01 00:00:00 +0800 2024",
                    "text": f"<a href='x'>link</a> post {i}",
                    "raw_text": f"post {i}",
                    "reposts_count": 1,
                    "comments_count": 2,
                    "attitudes_count": 3,
                    "isLongText": False,
                    "user": {
                        "id": 42,
                        "screen_name": "tester",
                        "gender": "m",
                        "verified": True,
                        "followers_count": 100,
                    },
                    "pics": [
                        {"pid": f"{i}_1", "large": {"url": f"https://img/{i}_1.jpg"}},
                    ],
                },
            }
        )
    return {
        "ok": 1,
        "data": {
            "cards": cards,
            "cardlistInfo": {"since_id": since_id} if since_id is not None else {},
        },
    }


def test_weibo_client_containerid(monkeypatch):
    uid = "123"
    cid = f"230413{uid}_-_WEIBO_PROFILE"

    def fake_request_json(self, path, params, referer=None):
        assert path == "/container/getIndex"
        assert params.get("type") == "uid"
        assert params.get("value") == uid
        return make_container_resp(uid, cid)

    monkeypatch.setattr(WeiboClient, "_request_json", fake_request_json, raising=True)

    client = WeiboClient()
    assert client.get_user_containerid(uid) == cid


def test_crawler_pagination_and_dedupe(monkeypatch, tmp_path):
    uid = "u100"
    cid = f"230413{uid}_-_WEIBO_PROFILE"
    # Map of (since_id) -> response data
    def fake_request_json(self, path, params, referer=None):
        if params.get("type") == "uid":
            return make_container_resp(uid, cid)
        # pages
        if params.get("containerid") == cid and "since_id" not in params:
            return make_page_resp(["1", "2"], since_id="cursor1")
        if params.get("containerid") == cid and params.get("since_id") == "cursor1":
            return make_page_resp(["2", "3"], since_id=None)
        raise AssertionError(f"unexpected params: {params}")

    monkeypatch.setattr(WeiboClient, "_request_json", fake_request_json, raising=True)

    service = WeiboCrawlerService()

    # ensure clean for this uid
    data_dir = service.storage_dir()
    if os.path.isdir(data_dir):
        prefix = f"{uid}."
        for f in os.listdir(data_dir):
            if f.startswith(prefix):
                os.remove(os.path.join(data_dir, f))

    result = service.crawl_user(uid=uid, max_pages=5, delay_s=0)
    assert result.containerid == cid
    assert result.stats.pages == 2
    assert result.stats.fetched == 3
    assert result.stats.written == 3

    # run again should write zero new due to seen set
    result2 = service.crawl_user(uid=uid, max_pages=5, delay_s=0)
    assert result2.stats.written == 0


def test_get_posts_pagination(tmp_path):
    # prepare jsonl
    uid = "u200"
    service = WeiboCrawlerService()
    jsonl = service.jsonl_path(uid)
    os.makedirs(os.path.dirname(jsonl), exist_ok=True)

    posts = [
        {"id": 1, "text": "a"},
        {"id": 2, "text": "b"},
        {"id": 3, "text": "c"},
    ]
    with open(jsonl, "w", encoding="utf-8") as fp:
        for p in posts:
            fp.write(json.dumps(p, ensure_ascii=False) + "\n")

    resp = weibo_controller.get_user_posts(None, uid=uid, limit=2, since_id=None)
    assert resp["status"] == 200
    data = resp["data"]
    assert len(data["posts"]) == 2
    next_id = data["next_since_id"]
    assert next_id == "2"

    resp2 = weibo_controller.get_user_posts(None, uid=uid, limit=2, since_id=next_id)
    assert resp2["status"] == 200
    data2 = resp2["data"]
    assert len(data2["posts"]) == 1
    assert data2["posts"][0]["id"] == 3
