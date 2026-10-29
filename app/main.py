"""快手大肥鱼 - DeepSeek 评论区自动回复机器人 CLI。

用法：
    python -m app.main --login      # 打开浏览器人工登录快手（登录态会持久化）
    python -m app.main --check      # 检查配置、登录态与数据统计
    python -m app.main --once       # 只执行一轮抓取 + 回复
    python -m app.main              # 持续运行（推荐）
"""
from __future__ import annotations

import argparse
import logging
import sys

from app.ai.engine import DeepSeekEngine
from app.browser.browser import BrowserManager
from app.browser.fetcher import CommentFetcher
from app.browser.sender import CommentSender
from app.config import ROOT, load_config, resolve_path
from app.db.store import Store
from app.scheduler.watcher import Watcher
from app.utils.logger import setup_logger


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="快手大肥鱼 - DeepSeek 评论区自动回复机器人")
    parser.add_argument("-c", "--config", default=None, help="配置文件路径（默认 config.yaml）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--login", action="store_true", help="仅打开浏览器人工登录快手")
    group.add_argument("--check", action="store_true", help="检查配置/登录态/数据统计后退出")
    group.add_argument("--once", action="store_true", help="只执行一轮抓取+回复")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = load_config(args.config)

    log_cfg = cfg["log"]
    setup_logger(log_cfg.get("level", "INFO"),
                 resolve_path(ROOT, log_cfg.get("file", "data/bot.log")))
    logger = logging.getLogger("ksfish")

    db_path = resolve_path(ROOT, cfg.get("db", {}).get("path", "data/bot.db"))
    store = Store(db_path)

    if args.check:
        return _check(cfg, logger)

    ai = DeepSeekEngine(cfg)
    if not ai.is_configured():
        logger.error("DeepSeek API Key 未配置，请在 config.yaml 的 deepseek.api_key 填写。")
        return 2

    logger.info("正在启动浏览器…")
    browser = BrowserManager(cfg)
    browser.start()
    try:
        if args.login:
            return _do_login(browser, logger)

        if not browser.is_logged_in():
            logger.info("检测到未登录，开始人工登录…")
            _do_login(browser, logger)

        fetcher = CommentFetcher(browser, cfg)
        sender = CommentSender(browser, cfg)
        watcher = Watcher(cfg, store, fetcher, sender, ai)

        if args.once:
            watcher.tick()
        else:
            logger.info("机器人已启动，Ctrl+C 停止。")
            try:
                watcher.run_forever()
            except KeyboardInterrupt:
                logger.info("收到 Ctrl+C，正常退出。")
        return 0
    finally:
        browser.stop()
        store.close()


def _do_login(browser: BrowserManager, logger) -> int:
    browser.open_login()
    logged = browser.is_logged_in()
    if logged:
        logger.info("登录成功，登录态已持久化到 %s", browser.cfg["browser"]["user_data_dir"])
    else:
        logger.warning("未检测到登录 Cookie，请确认浏览器窗口内已完成登录。")
        return 1
    return 0


def _check(cfg: dict, logger) -> int:
    logger.info("=== 配置检查 ===")
    ai = DeepSeekEngine(cfg)
    logger.info("DeepSeek: %s 已配置=%s 模型=%s",
                cfg["deepseek"]["base_url"], ai.is_configured(), cfg["deepseek"]["model"])
    photos = cfg["creator"].get("photo_urls", [])
    logger.info("监控作品数: %d", len(photos))
    for u in photos:
        logger.info("  - %s", u)

    db_path = resolve_path(ROOT, cfg.get("db", {}).get("path", "data/bot.db"))
    store = Store(db_path)
    st = store.stats()
    logger.info("SQLite 数据: 共 %d 条评论，已回复 %d，已忽略 %d",
                st["total"], st["replied"], st["ignored"])
    store.close()
    logger.info("=== 登录态检查（需要浏览器环境） ===")
    browser = BrowserManager(cfg)
    browser.start()
    try:
        if browser.is_logged_in():
            logger.info("快手登录态: 已登录")
        else:
            logger.info("快手登录态: 未登录，请先运行 `python -m app.main --login`")
    finally:
        browser.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
