"""日志初始化。"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logger(level: str = "INFO", file: str | None = None) -> logging.Logger:
    logger = logging.getLogger("ksfish")
    if logger.handlers:
        return logger

    logger.setLevel(level.upper())
    formatter = logging.Formatter(_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    if file:
        path = Path(file)
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger
