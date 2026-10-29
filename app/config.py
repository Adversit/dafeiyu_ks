"""配置加载与访问。

配置文件为项目根目录 config.yaml，可用 --config 指定其他路径。
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def default_config_path() -> Path:
    return ROOT / "config.yaml"


def load_config(path: str | os.PathLike | None = None) -> dict:
    cfg_path = Path(path) if path else default_config_path()
    if not cfg_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    _ensure_defaults(cfg)
    return cfg


def _ensure_defaults(cfg: dict) -> None:
    cfg.setdefault("deepseek", {}).setdefault("base_url", "https://api.deepseek.com")
    cfg.setdefault("deepseek", {}).setdefault("model", "deepseek-chat")
    cfg.setdefault("browser", {}).setdefault("user_data_dir", "data/chrome-profile")
    cfg.setdefault("browser", {}).setdefault("headless", False)
    cfg.setdefault("bot", {})
    cfg.setdefault("selectors", {})
    cfg.setdefault("log", {})


def resolve_path(root: Path, value: str) -> Path:
    """将 config 里的相对路径解析为相对项目根目录的绝对路径。"""
    p = Path(value)
    return p if p.is_absolute() else (root / p)
