"""评论与回复记录的数据访问层（sqlite3，标准库实现）。

职责：
- 评论去重入库（同一 photo_id + comment_id 只存一次）
- 查询未回复评论
- 回复后标记，用于复制回复次数/频率限制
- 保存 bot_state（如每日计数等轻量 KV）
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from app.db.models import check_schema


class Store:
    def __init__(self, db_path: str | Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        check_schema(self.conn)

    # ---------- 评论 ----------

    def upsert_comment(self, photo_id: str, comment_id: str, user_name: str,
                       text: str, parent_id: str = "") -> bool:
        """插入新评论；已存在则忽略。返回是否为新评论。"""
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO comments
               (photo_id, comment_id, user_name, text, parent_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (photo_id, comment_id, user_name, text, parent_id,
             datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def get_unreplied(self, limit: int = 50) -> list[tuple]:
        return self.conn.execute(
            """SELECT id, photo_id, comment_id, user_name, text, parent_id
               FROM comments WHERE replied = 0 ORDER BY id ASC LIMIT ?""",
            (limit,),
        ).fetchall()

    def get_unreplied_for_photo(self, photo_id: str, limit: int = 50) -> list[tuple]:
        return self.conn.execute(
            """SELECT id, photo_id, comment_id, user_name, text, parent_id
               FROM comments WHERE photo_id = ? AND replied = 0
               ORDER BY id ASC LIMIT ?""",
            (photo_id, limit),
        ).fetchall()

    def mark_replied(self, cid: int, reply_text: str, status: int = 1) -> None:
        """status: 1=已回复, 2=已忽略（命中过滤规则，不再处理）。"""
        self.conn.execute(
            """UPDATE comments SET replied = ?, reply_text = ?, reply_at = ?
               WHERE id = ?""",
            (status, reply_text, datetime.now().isoformat(timespec="seconds"), cid),
        )
        self.conn.commit()

    def replied_count(self, since: str | None = None) -> int:
        if since:
            row = self.conn.execute(
                "SELECT COUNT(*) FROM comments WHERE replied = 1 AND reply_at >= ?",
                (since,),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) FROM comments WHERE replied = 1").fetchone()
        return row[0]

    def last_reply_at(self) -> str | None:
        row = self.conn.execute(
            "SELECT MAX(reply_at) FROM comments WHERE replied = 1").fetchone()
        return row[0] or None

    def stats(self) -> dict:
        total, replied, ignored = self.conn.execute(
            """SELECT COUNT(*),
                      COALESCE(SUM(CASE WHEN replied = 1 THEN 1 ELSE 0 END), 0),
                      COALESCE(SUM(CASE WHEN replied = 2 THEN 1 ELSE 0 END), 0)
               FROM comments""").fetchone()
        return {"total": total, "replied": replied, "ignored": ignored}

    # ---------- bot_state KV ----------

    def get_state(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def set_state(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO bot_state(key, value) VALUES (?, ?)",
            (key, value),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
