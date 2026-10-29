"""Prompt 构建：把人设、评论上下文组装成 DeepSeek 的 system/user 消息。"""
from __future__ import annotations

from app.ai.persona import get_persona


def build_system(cfg: dict) -> str:
    bot = cfg["bot"]
    persona = get_persona(bot["persona"])
    emoji_rule = "可以在合适位置使用 emoji。" if bot.get("emoji", True) else "禁止使用 emoji。"

    return (
        f"【身份】{persona['identity']}\n"
        f"【风格】{persona['style']}\n"
        f"【规则】你是该作品作者，正在回复粉丝在评论区对你说的话。"
        f"只回复这条评论的内容，不要臆想不存在的对话。{emoji_rule}"
        f"不要使用 Markdown 格式，不要加引号，直接输出要发送的正文。"
    )


def build_user(cfg: dict, comment_text: str, user_name: str,
               parent_text: str = "", video_caption: str = "") -> str:
    parts = []
    if video_caption:
        parts.append(f"视频标题/文案：{video_caption}")
    if parent_text:
        parts.append(f"该评论是在回复别人，别人原话：{parent_text}")
    parts.append(f"粉丝 {user_name} 评论说：{comment_text}")
    max_len = int(cfg["bot"].get("max_reply_length", 60))
    parts.append(f"请以作者口吻回复，控制在 {max_len} 字以内，输出回复正文。")
    return "\n".join(parts)
