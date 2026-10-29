"""主循环：抓取评论 → 入库去重 → AI 生成回复 → 发送 → 标记结果。

以“作品页驱动”的方式执行：每次进入一个作品页，
先抓取并入库该页新评论，再就地回复该作品尚未回复的评论，
减少页面切换带来的不稳定。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from app.ai.engine import DeepSeekEngine, DeepSeekError
from app.ai.prompts import build_system, build_user
from app.utils.humanize import human_delay, human_pause

logger = logging.getLogger("ksfish.watcher")


class RateLimiter:
    """基于最近 1 小时 / 今日已回复数量的频率限制。"""

    def __init__(self, cfg: dict, store):
        self.cfg = cfg
        self.store = store

    def over_limit(self) -> bool:
        bot = self.cfg["bot"]
        now = datetime.now()
        hour_start = (now - timedelta(hours=1)).isoformat(timespec="seconds")
        day_start = now.strftime("%Y-%m-%dT00:00:00")
        hour_count = self.store.replied_count(since=hour_start)
        day_count = self.store.replied_count(since=day_start)
        if hour_count >= int(bot.get("max_replies_per_hour", 10)):
            logger.info("已达每小时回复上限 %s，本轮不再回复", bot.get("max_replies_per_hour"))
            return True
        if day_count >= int(bot.get("max_replies_per_day", 200)):
            logger.info("已达每日回复上限 %s，本轮不再回复", bot.get("max_replies_per_day"))
            return True
        return False


class Watcher:
    def __init__(self, cfg: dict, store, fetcher, sender, ai: DeepSeekEngine):
        self.cfg = cfg
        self.store = store
        self.fetcher = fetcher
        self.sender = sender
        self.ai = ai
        self.rate = RateLimiter(cfg, store)

    # ---------- 主入口 ----------

    def run_forever(self) -> None:
        interval = int(self.cfg["bot"].get("poll_interval_seconds", 120))
        while True:
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                logger.exception("本轮执行出现异常，继续下一轮")
            logger.info("休息 %s 秒后进入下一轮…", interval)
            time.sleep(interval)

    def tick(self) -> None:
        if not self.cfg["bot"].get("enabled", True):
            logger.info("bot.enabled=false，跳过本轮")
            return
        for url in self.cfg["creator"].get("photo_urls", []):
            self.process_photo(url)

    # ---------- 单个作品 ----------

    def process_photo(self, url: str) -> None:
        photo_id, comments = self.fetcher.fetch_photo(url)
        new_count = 0
        for c in comments:
            is_new = self.store.upsert_comment(
                photo_id, c["comment_id"], c["user_name"],
                c["text"], c.get("parent_id", ""),
            )
            if is_new:
                new_count += 1
                logger.info("新评论 @%s：%s", c["user_name"], c["text"][:30])
        if new_count:
            logger.info("作品 %s 新增 %d 条评论", photo_id, new_count)

        if not self.cfg["bot"].get("auto_reply", True):
            return

        human_pause(3, 6)
        rows = self.store.get_unreplied_for_photo(photo_id, limit=20)
        for row in rows:
            if self.rate.over_limit():
                return
            cid, _, _, user, text, parent_id = row
            if not self._needs_reply(text):
                self.store.mark_replied(cid, "", status=2)
                continue
            reply = self._generate(text, user)
            if not reply:
                logger.warning("AI 未生成有效回复，稍后重试 @%s", user)
                continue

            human_delay(
                float(self.cfg["bot"].get("reply_interval_min", 20)),
                float(self.cfg["bot"].get("reply_interval_max", 60)),
            )
            comment = {
                "comment_id": row[2],
                "user_name": user,
                "text": text,
                "parent_id": parent_id,
            }
            ok = self.sender.reply_to_comment(comment, reply)
            if ok:
                self.store.mark_replied(cid, reply, status=1)

    # ---------- 规则 ----------

    def _needs_reply(self, text: str) -> bool:
        bot = self.cfg["bot"]
        if any(k and k in text for k in bot.get("filter_keywords", [])):
            logger.info("命中过滤关键词，忽略该评论: %s", text[:20])
            return False
        triggers = bot.get("trigger_keywords", [])
        if triggers and not any(t and t in text for t in triggers):
            return False
        return True

    def _generate(self, text: str, user: str) -> str:
        system = build_system(self.cfg)
        prompt = build_user(self.cfg, text, user)
        try:
            reply = self.ai.chat(system, prompt)
        except DeepSeekError as e:
            logger.warning("AI 生成失败: %s", e)
            return ""
        max_len = int(self.cfg["bot"].get("max_reply_length", 60))
        if len(reply) > int(max_len * 1.5):
            reply = reply[:max_len]
        return reply.strip()
