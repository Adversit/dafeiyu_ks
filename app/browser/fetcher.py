"""作品页评论区抓取（快手网页版前台）。

快手网页版作品 URL 形如：
    https://www.kuaishou.com/short-video/{photo_id}
    https://www.kuaishou.com/fw/photo/{photo_id}
评论区为懒加载滚动 + “查看更多”按钮展开。
"""
from __future__ import annotations

import hashlib
import logging
import re

from app.utils.humanize import human_delay, human_pause

logger = logging.getLogger("ksfish.fetcher")

_PHOTO_ID_RE = re.compile(r"/(?:short\-video|video|photoview|photo|fw/photo)/([A-Za-z0-9_\-]+)")


def extract_photo_id(url: str) -> str:
    m = _PHOTO_ID_RE.search(url)
    if m:
        return m.group(1)
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:16]


class CommentFetcher:
    def __init__(self, browser, cfg: dict):
        self.page = browser.page
        self.sel = cfg["selectors"]
        self.max_scrolls = int(cfg["creator"].get("max_scrolls", 20))

    def fetch_photo(self, url: str) -> tuple[str, list[dict]]:
        """抓取单个作品页的一级评论，返回 (photo_id, comments)。

        comments 元素: {"comment_id", "user_name", "text", "parent_id"}
        """
        photo_id = extract_photo_id(url)
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        human_pause(2, 4)
        self._open_comments()
        for _ in range(self.max_scrolls):
            if not self._scroll_more():
                break
            human_delay(1, 2)
        comments = self._extract_comments()
        logger.info("作品 %s 抓到 %d 条评论", photo_id, len(comments))
        return photo_id, comments

    # ---------- 内部 ----------

    def _open_comments(self) -> None:
        try:
            btn = self.page.locator(self.sel["load_more_btn"]).first
            if btn.is_visible(timeout=3000):
                btn.click()
                human_pause(1, 2)
        except Exception:  # noqa: BLE001
            pass

    def _count_comments(self) -> int:
        try:
            return self.page.locator(self.sel["comment_item"]).count()
        except Exception:  # noqa: BLE001
            return 0

    def _scroll_more(self) -> bool:
        """滚动到底 + 尝试点“查看更多”，返回是否有新增评论。"""
        before = self._count_comments()
        self.page.mouse.wheel(0, 20000)
        human_delay(1.5, 3)
        try:
            btn = self.page.locator(self.sel["load_more_btn"]).first
            if btn.is_visible(timeout=1500):
                btn.click()
                human_pause(1, 2)
        except Exception:  # noqa: BLE001
            pass
        after = self._count_comments()
        return after > before

    def _extract_comments(self) -> list[dict]:
        comments: list[dict] = []
        items = self.page.locator(self.sel["comment_item"]).all()
        for it in items:
            user = self._safe_text(it.locator(self.sel["comment_user"]).first)
            text = self._safe_text(it.locator(self.sel["comment_text"]).first)
            if not text:
                continue
            cid = self._find_id(it) or self._hash_id(user, text)
            comments.append({
                "comment_id": cid,
                "user_name": user,
                "text": text,
                "parent_id": "",
            })
        return comments

    @staticmethod
    def _safe_text(locator) -> str:
        try:
            if locator.is_visible(timeout=500):
                return locator.inner_text().strip()
        except Exception:  # noqa: BLE001
            pass
        return ""

    @staticmethod
    def _find_id(item) -> str:
        for attr in ("data-commentid", "data-comment-id", "data-id", "data-cid", "commentid"):
            v = item.get_attribute(attr)
            if v:
                return v
        return ""

    @staticmethod
    def _hash_id(user: str, text: str) -> str:
        return "h_" + hashlib.md5(f"{user}|{text}".encode("utf-8")).hexdigest()[:24]
