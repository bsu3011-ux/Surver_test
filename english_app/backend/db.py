import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "app.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS user_profile (
            id INTEGER PRIMARY KEY DEFAULT 1,
            level_code TEXT,
            level_label TEXT,
            score INTEGER,
            total INTEGER,
            assessed_at TEXT,
            daily_vocab_count INTEGER,
            learning_mode TEXT DEFAULT 'general'
        );

        CREATE TABLE IF NOT EXISTS vocab_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            english TEXT,
            pronunciation TEXT,
            korean TEXT,
            part_of_speech TEXT,
            example_en TEXT,
            example_ko TEXT,
            tip TEXT,
            type TEXT DEFAULT 'word',
            level_code TEXT,
            created_date TEXT,
            review_count INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS quiz_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            correct INTEGER,
            total INTEGER,
            level_code TEXT
        );

        CREATE TABLE IF NOT EXISTS study_days (
            date TEXT PRIMARY KEY
        );
    """)

    # 기존 DB에 learning_mode 컬럼 추가 (마이그레이션)
    try:
        cur.execute("ALTER TABLE user_profile ADD COLUMN learning_mode TEXT DEFAULT 'general'")
        conn.commit()
    except Exception:
        pass  # 이미 존재하면 무시

    conn.commit()
    conn.close()
