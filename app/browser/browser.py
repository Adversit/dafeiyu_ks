"""Playwright 浏览器与持久化登录态管理。

使用 launch_persistent_context 复用 user_data_dir：
- 登录一次（扫码/账号密码）后 Cookie 与 LocalStorage 全部持久化
- 每次启动无需重新登录
"""
from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import sync_playwright

logger = logging.getLogger("ksfish.browser")

_HOME_URL = "https://www.kuaishou.com/?isHome=1"
_COOKIE_MARKERS = ("userId", "passToken", "kuaishou.server.web_st", "kuaishou.server.st")


class BrowserManager:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._pw = None
        self.context = None
        self.page = None

    def start(self) -> "BrowserManager":
        bcfg = self.cfg["browser"]
        data_dir = Path(bcfg["user_data_dir"])
        data_dir.mkdir(parents=True, exist_ok=True)

        self._pw = sync_playwright().start()
        self.context = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(data_dir),
            headless=bcfg.get("headless", False),
            slow_mo=bcfg.get("slow_mo", 80),
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.set_default_timeout(int(bcfg.get("default_timeout", 15000)))
        logger.info("浏览器已启动（headless=%s）", bcfg.get("headless", False))
        return self

    def stop(self) -> None:
        try:
            if self.context:
                self.context.close()
        except Exception as e:  # noqa: BLE001
            logger.debug("关闭上下文异常: %s", e)
        finally:
            if self._pw:
                self._pw.stop()

    # ---------- 登录态 ----------

    def is_logged_in(self) -> bool:
        """通过快手域 Cookie 判断是否已登录。"""
        try:
            cookies = self.context.cookies(_HOME_URL)
        except Exception as e:  # noqa: BLE001
            logger.debug("读取 Cookie 失败: %s", e)
            return False
        names = {c["name"] for c in cookies}
        return any(m in names for m in _COOKIE_MARKERS)

    def open_login(self) -> None:
        """打开首页等待用户人工登录。"""
        self.page.goto(_HOME_URL, wait_until="domcontentloaded", timeout=60000)
        logger.info("请在浏览器中登录快手账号，登录完成后按回车继续…")
        input("登录完成后按回车继续。")
        self.page.screenshot(path=Path(self.cfg["browser"]["user_data_dir"]) / "logged-in.png")

    def open_photo(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
