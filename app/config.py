"""配置加载与访问。

配置文件为项目根目录 config.yaml，可用 --config 指定其他路径。
提供照片 URL 增改接口（保留原注释的文本级写入）。
"""
from __future__ import annotations

import os
import re
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


# ---------------------------------------------------------------------------
# 文本级写入：以行编辑方式修改 config.yaml，保留原有注释，避免 YAML 重写丢注释
# ---------------------------------------------------------------------------

_PLACEHOLDER_ID = "REPLACE_WITH_PHOTO_ID"


def set_api_key_write(cfg_path: Path, api_key: str) -> tuple[bool, str]:
    """把 DeepSeek API Key 写入 deepseek.api_key（保留行尾注释）。"""
    text = cfg_path.read_text(encoding="utf-8")
    new_text, n = re.subn(
        r'^(\s*api_key:\s*)(?:"[^"]*"|\S*)',
        lambda m: f'{m.group(1)}"{api_key}"',
        text,
        count=1,
        flags=re.M,
    )
    if n != 1:
        return False, "config.yaml 中未找到 api_key 字段"
    cfg_path.write_text(new_text, encoding="utf-8")
    return True, "api_key 已写入 config.yaml"


def add_photo_write(cfg_path: Path, url: str) -> tuple[bool, str]:
    """把作品 URL 追加进 photo_urls；首次会用真实 URL 替换占位符行。"""
    text = cfg_path.read_text(encoding="utf-8")
    if url in text:
        return False, "该 URL 已存在于 photo_urls，跳过"
    line = f'    - "{url}"'

    if _PLACEHOLDER_ID in text:
        new_text, n = re.subn(
            r'^(\s*)-\s*"[^"]*' + _PLACEHOLDER_ID + r'[^"]*"',
            lambda m: line,
            text,
            count=1,
            flags=re.M,
        )
        if n != 1:
            return False, "替换占位符失败"
        cfg_path.write_text(new_text, encoding="utf-8")
        return True, "已替换占位符，URL 已写入 photo_urls"

    new_text = _append_under_photo_urls(text, line)
    cfg_path.write_text(new_text, encoding="utf-8")
    return True, "URL 已追加到 photo_urls"


def _append_under_photo_urls(text: str, line: str) -> str:
    """在 photo_urls 列表块的最后一项后插入一行（保持缩进与块结构）。"""
    lines = text.splitlines(keepends=True)
    idx = next(
        (i for i, l in enumerate(lines) if l.strip().startswith("photo_urls:")),
        None,
    )
    if idx is None:
        raise ValueError("config.yaml 中未找到 photo_urls 块")

    base_indent = len(lines[idx]) - len(lines[idx].lstrip())
    last_child = idx
    seen_blank = False
    j = idx + 1
    while j < len(lines):
        raw = lines[j]
        stripped = raw.strip()
        if not stripped:
            seen_blank = True
            j += 1
            continue
        cur_indent = len(raw) - len(raw.lstrip())
        if stripped.startswith("#"):
            if seen_blank:
                break
            j += 1
            continue
        if cur_indent <= base_indent:
            break
        last_child = j
        seen_blank = False
        j += 1

    lines.insert(last_child + 1, line + "\n")
    return "".join(lines)
