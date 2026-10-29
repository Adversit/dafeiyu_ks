"""DeepSeek API 封装。

统一走 OpenAI 兼容的 /chat/completions 协议，base_url 可替换，
但按本项目约定默认只接 DeepSeek。
"""
from __future__ import annotations

import re

import requests


class DeepSeekError(Exception):
    pass


class DeepSeekEngine:
    def __init__(self, cfg: dict):
        dcfg = cfg["deepseek"]
        self.api_key = dcfg["api_key"].strip()
        self.base_url = dcfg["base_url"].rstrip("/")
        self.model = dcfg["model"]
        self.temperature = float(dcfg.get("temperature", 1.3))
        self.max_tokens = int(dcfg.get("max_tokens", 256))
        self.timeout = float(dcfg.get("timeout", 60))

    def is_configured(self) -> bool:
        return bool(self.api_key) and self.api_key.lower() != "sk-xxxx"

    def chat(self, system: str, user: str, max_tokens: int | None = None,
             temperature: float | None = None) -> str:
        if not self.is_configured():
            raise DeepSeekError(
                "DeepSeek API Key 未配置，请在 config.yaml 的 deepseek.api_key 填入")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "stream": False,
        }
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise DeepSeekError(f"DeepSeek API 请求失败: {e}") from e

        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise DeepSeekError(f"DeepSeek API 响应异常: {data}") from e

        return self._clean(content)

    @staticmethod
    def _clean(content: str) -> str:
        """剥离 DeepSeek-R1 的思考过程标记与多余空白。"""
        text = content.strip()
        text = re.sub(r"<[/]?think(ing)?>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"start_thought.*?end_thought", "", text,
                      flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        return text.strip()
