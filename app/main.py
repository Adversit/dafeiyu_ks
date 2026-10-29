"""快手大肥鱼 - DeepSeek 评论区自动回复机器人 CLI。

用法：
    python -m app.main --setup                     # 交互式补齐缺失配置（API Key/作品链接）
    python -m app.main --set-api-key sk-xxx        # 直接把 DeepSeek API Key 写入 config.yaml
    python -m app.main --add-photo URL [URL...]    # 把作品链接追加到 config.yaml 的 photo_urls
    python -m app.main --login                     # 打开浏览器人工登录快手（登录态会持久化）
    python -m app.main --check                     # 检查配置、登录态与数据统计
    python -m app.main --once                      # 只执行一轮抓取 + 回复
    python -m app.main                             # 持续运行（未登录会自动引导登录）
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.ai.engine import DeepSeekEngine
from app.browser.browser import BrowserManager
from app.browser.fetcher import CommentFetcher
from app.browser.sender import CommentSender
from app.config import (
    ROOT,
    add_photo_write,
    default_config_path,
    load_config,
    resolve_path,
    set_api_key_write,
)
from app.db.store import Store
from app.scheduler.watcher import Watcher
from app.utils.logger import setup_logger


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="快手大肥鱼 - DeepSeek 评论区自动回复机器人")
    parser.add_argument("-c", "--config", default=None, help="配置文件路径（默认 config.yaml）")
    parser.add_argument("--add-photo", metavar="URL", action="append", dest="add_photos",
                        help="把快手作品链接追加到 config.yaml（可重复）")
    parser.add_argument("--set-api-key", metavar="KEY", dest="api_key",
                        help="把 DeepSeek API Key 写入 config.yaml")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--setup", action="store_true",
                       help="交互式补齐缺失配置（API Key/作品链接）后退出")
    group.add_argument("--login", action="store_true", help="仅打开浏览器人工登录快手")
    group.add_argument("--check", action="store_true", help="检查配置/登录态/数据统计后退出")
    group.add_argument("--once", action="store_true", help="只执行一轮抓取+回复")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg_path = Path(args.config) if args.config else default_config_path()

    # ---- 配置操作：不启动浏览器，处理完即退出 ----
    if args.add_photos or args.api_key or args.setup:
        try:
            return _config_ops(cfg_path, args)
        except (ValueError, FileNotFoundError) as e:
            print(f"[错误] {e}")
            return 1

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
        logger.error("DeepSeek API Key 未配置，请先运行：python -m app.main --setup")
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


# ---------------------------------------------------------------------------
# 配置写入 / 交互补齐
# ---------------------------------------------------------------------------

def _config_ops(cfg_path: Path, args: argparse.Namespace) -> int:
    if args.api_key:
        ok, msg = set_api_key_write(cfg_path, args.api_key)
        print(f"[api_key] {msg}")
        if not ok:
            return 1
    if args.add_photos:
        for u in args.add_photos:
            ok, msg = add_photo_write(cfg_path, u)
            print(f"[photo] {msg}")
    if args.setup:
        return _setup(cfg_path)
    return 0


def _setup(cfg_path: Path) -> int:
    try:
        cfg = load_config(cfg_path)
    except FileNotFoundError:
        cfg = {}
    changed: list[str] = []

    print("== 快手大肥鱼 配置向导 ==")

    key = cfg.get("deepseek", {}).get("api_key", "")
    if not key or "sk-xxxx" in key:
        print("\n未检测到 DeepSeek API Key。")
        k = input("请粘贴 DeepSeek API Key（sk-…，直接回车跳过）：").strip()
        if k:
            ok, msg = set_api_key_write(cfg_path, k)
            print(f"  -> {msg}")
            if ok:
                changed.append("api_key")
    else:
        print(f"\nDeepSeek API Key 已配置：{key[:6]}…{key[-4:]}")

    photos = cfg.get("creator", {}).get("photo_urls", [])
    need_photos = not photos or any("REPLACE_WITH_PHOTO_ID" in p for p in photos)
    if need_photos:
        print("\n未配置要监控的作品评论区链接。")
        print("请粘贴快手作品页地址（每行一个，空行结束，例如 https://www.kuaishou.com/short-video/xxx）：")
        added = 0
        while True:
            u = input("作品链接 > ").strip()
            if not u:
                break
            if not u.startswith("http"):
                print("  [警告] 未以 http 开头，已忽略。")
                continue
            ok, msg = add_photo_write(cfg_path, u)
            print(f"  -> {msg}")
            if ok:
                added += 1
        if added:
            changed.append(f"photo_urls +{added}")
    else:
        print(f"\n已配置 {len(photos)} 个监控作品。")

    if not changed:
        print("\n配置无需修改，全部就绪。")
    else:
        print(f"\n配置已更新：{', '.join(changed)}")
    print("后续步骤：python -m app.main --login（登录）→ python -m app.main（运行）")
    return 0


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
