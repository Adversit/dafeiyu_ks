"""楼中楼回复与表情包发送。

参考 douyin-comment-reply 的经验教训：
- 回复输入框可能出现在评论容器之外，需全页定位
- 页面可能同时存在多个“发送”按钮（顶部发新评论 / 评论内回复），
  需选择离输入框最近、最靠近页面底部的那一个
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from app.config import ROOT
from app.utils.humanize import human_delay, human_pause, human_type

logger = logging.getLogger("ksfish.sender")


class CommentSender:
    def __init__(self, browser, cfg: dict):
        self.page = browser.page
        self.cfg = cfg
        self.sel = cfg["selectors"]
        self.bot = cfg["bot"]
        sticker = self.bot.get("sticker_path", "")
        self.sticker_path = Path(sticker) if sticker else Path()

    # ---------- 公开入口 ----------

    def reply_to_comment(self, comment: dict, reply_text: str) -> bool:
        """在**当前页面**的评论列表中找到目标评论并发送楼中楼回复。"""
        target = self._find_comment_item(comment)
        if target is None:
            logger.warning(
                "未在页面找到目标评论 user=%s text=%s…",
                comment["user_name"], comment["text"][:20])
            self._screenshot("notfound")
            return False

        if not self._click_reply_btn(target):
            self._screenshot("no_reply_btn")
            return False

        human_pause(0.8, 1.5)
        box = self._find_reply_box()
        if box is None:
            logger.warning("未找到回复输入框（页面可能已弹出或结构变化）")
            self._screenshot("no_input_box")
            return False

        if self._sticker_ready():
            self._try_attach_sticker()

        human_type(box, reply_text)
        human_delay(0.5, 1.2)
        sent = self._click_send()

        human_pause(1, 2)
        ok = sent and self._verify_sent(box)
        if ok:
            logger.info("已回复 @%s：%s", comment["user_name"], reply_text)
        else:
            logger.info("回复可能失败 user=%s", comment["user_name"])
            self._screenshot("send_failed")
        return ok

    # ---------- 定位 ----------

    def _find_comment_item(self, comment: dict):
        items = self.page.locator(self.sel["comment_item"]).all()
        for it in items:
            if self._match_id(it, comment["comment_id"]):
                return it
        # fallback：评论文本匹配
        for it in items:
            try:
                t = it.locator(self.sel["comment_text"]).first
                if comment["text"] and comment["text"] in (t.inner_text(timeout=1000) or ""):
                    return it
            except Exception:  # noqa: BLE001
                continue
        return None

    @staticmethod
    def _match_id(item, cid: str) -> bool:
        if not cid or cid.startswith("h_"):
            return False
        for attr in ("data-commentid", "data-comment-id", "data-id", "data-cid"):
            v = item.get_attribute(attr)
            if v and cid in v:
                return True
        return False

    def _click_reply_btn(self, target) -> bool:
        try:
            btn = target.locator(self.sel["reply_btn"]).first
            if not btn.is_visible(timeout=1500):
                target.hover()
                human_delay(0.5, 1)
            btn.click()
            return True
        except Exception as e:  # noqa: BLE001
            logger.debug("点击回复按钮失败: %s", e)
            return False

    def _find_reply_box(self):
        loc = self.page.locator(self.sel["input_box"])
        cands = []
        n = loc.count()
        for i in range(n):
            box = loc.nth(i)
            try:
                if box.is_visible(timeout=500):
                    cands.append(box)
            except Exception:  # noqa: BLE001
                continue
        if not cands:
            return None
        if len(cands) == 1:
            return cands[0]
        # 多个输入框时，取页面最下方那个（当前回复框通常在下半区）
        cands.sort(key=lambda b: (b.bounding_box() or {"y": 0})["y"])
        return cands[-1]

    # ---------- 发送 ----------

    def _click_send(self) -> bool:
        btns = self.page.locator(self.sel["send_btn"])
        n = btns.count()
        # 从最后一个可见按钮倒序找（回复按钮通常更深/更靠底部）
        for i in range(n - 1, -1, -1):
            b = btns.nth(i)
            try:
                if b.is_visible(timeout=500):
                    b.click()
                    return True
            except Exception:  # noqa: BLE001
                continue
        logger.warning("未找到可见的发送按钮")
        return False

    def _verify_sent(self, box) -> bool:
        try:
            if box.input_value() == "":
                return True
        except Exception:  # noqa: BLE001
            pass
        try:
            if (box.inner_text() or "").strip() == "":
                return True
        except Exception:  # noqa: BLE001
            pass
        return False

    # ---------- 表情包 ----------

    def _sticker_ready(self) -> bool:
        if not self.bot.get("sticker", True):
            return False
        return self.sticker_path.exists()

    def _try_attach_sticker(self) -> None:
        try:
            up = self.page.locator(self.sel["upload_input"])
            if up.count() == 0:
                logger.info("页面无图片上传框，跳过表情包")
                return
            up.first.set_input_files(str(self.sticker_path))
            human_pause(1, 2)
            logger.info("已附加表情包 %s", self.sticker_path.name)
        except Exception as e:  # noqa: BLE001
            logger.warning("附加表情包失败（继续发文字）: %s", e)

    # ---------- 调试 ----------

    def _screenshot(self, name: str) -> None:
        try:
            d = ROOT / "data" / "screenshots"
            d.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=d / f"{name}-{int(time.time())}.png")
            logger.info("已保存调试截图: %s", d)
        except Exception as e:  # noqa: BLE001
            logger.debug("截图失败: %s", e)
