"""故事库：用 SQLite 保存故事和声音配置。

每次操作都新开一个连接，避免多线程下共享连接的问题。
"""

import sqlite3
from datetime import datetime

import config


def _connect():
    conn = sqlite3.connect(str(config.DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    config.ensure_dirs()
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS voices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                wav_path TEXT NOT NULL,
                ref_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                topic TEXT NOT NULL DEFAULT '',
                age INTEGER NOT NULL DEFAULT 4,
                voice_id INTEGER,
                audio_path TEXT,
                tts_engine TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (voice_id) REFERENCES voices(id)
            );
            """
        )


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- 声音 ----------
def add_voice(name: str, wav_path: str, ref_text: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO voices (name, wav_path, ref_text, created_at) VALUES (?, ?, ?, ?)",
            (name, wav_path, ref_text, _now()),
        )
        return int(cur.lastrowid)


def list_voices():
    with _connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM voices ORDER BY id DESC")]


def get_voice(voice_id: int):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM voices WHERE id = ?", (voice_id,)).fetchone()
        return dict(row) if row else None


# ---------- 故事 ----------
def add_story(title: str, body: str, topic: str, age: int) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO stories (title, body, topic, age, created_at) VALUES (?, ?, ?, ?, ?)",
            (title, body, topic, age, _now()),
        )
        return int(cur.lastrowid)


def list_stories():
    with _connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM stories ORDER BY id DESC")]


def get_story(story_id: int):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
        return dict(row) if row else None


def set_story_audio(story_id: int, audio_path: str, engine: str):
    with _connect() as conn:
        conn.execute(
            "UPDATE stories SET audio_path = ?, tts_engine = ? WHERE id = ?",
            (audio_path, engine, story_id),
        )