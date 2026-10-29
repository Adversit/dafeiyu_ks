"""人类行为模拟：随机延迟、逐字输入、随机停顿，降低被风控的概率。"""
from __future__ import annotations

import random
import time


def human_delay(lo: float = 0.5, hi: float = 1.5) -> None:
    time.sleep(random.uniform(lo, hi))


def human_pause(lo: float = 1.0, hi: float = 3.0) -> None:
    time.sleep(random.uniform(lo, hi))


def random_jitter(base: float, ratio: float = 0.3) -> float:
    return random.uniform(base * (1 - ratio), base * (1 + ratio))


def human_type(locator, text: str, delay: float = 0.04) -> None:
    """逐字符输入中文/英文文本，模拟真人打字节奏。"""
    locator.click()
    for ch in text:
        locator.type(ch)
        time.sleep(random.uniform(delay * 0.5, delay * 1.8))


def should_slow_down(consecutive_ops: int) -> bool:
    return consecutive_ops >= 5
