"""SQLite 表结构定义。"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id    TEXT NOT NULL DEFAULT '',
    comment_id  TEXT NOT NULL,
    user_name   TEXT NOT NULL DEFAULT '',
    text        TEXT NOT NULL DEFAULT '',
    parent_id   TEXT NOT NULL DEFAULT '',
    replied     INTEGER NOT NULL DEFAULT 0,
    reply_text  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT '',
    reply_at    TEXT NOT NULL DEFAULT '',
    UNIQUE(photo_id, comment_id)
);

CREATE INDEX IF NOT EXISTS idx_comments_replied ON comments(replied);
CREATE INDEX IF NOT EXISTS idx_comments_created ON comments(created_at);

CREATE TABLE IF NOT EXISTS bot_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
"""


def check_schema(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
