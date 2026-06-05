import json
import sqlite3
import random
import hmac
import hashlib
import subprocess
import os
from datetime import date, datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "progress.db"
WORDS_PATH = BASE_DIR / "data" / "words.json"

app = FastAPI(title="말해보카")

# ── DB 초기화 ─────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_stats (
            id INTEGER PRIMARY KEY DEFAULT 1,
            diamonds INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            last_study_date TEXT DEFAULT '',
            league TEXT DEFAULT 'bronze',
            total_correct INTEGER DEFAULT 0,
            total_wrong INTEGER DEFAULT 0
        );
        INSERT OR IGNORE INTO user_stats (id) VALUES (1);

        CREATE TABLE IF NOT EXISTS word_progress (
            word_id INTEGER PRIMARY KEY,
            correct INTEGER DEFAULT 0,
            wrong INTEGER DEFAULT 0,
            is_bookmarked INTEGER DEFAULT 0,
            last_seen TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS daily_log (
            log_date TEXT PRIMARY KEY,
            questions INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0
        );
        """)

init_db()

# ── 단어 로딩 ─────────────────────────────────────────────
def load_words():
    with open(WORDS_PATH, encoding="utf-8") as f:
        return json.load(f)

WORDS = load_words()
WORDS_MAP = {w["id"]: w for w in WORDS}

# ── 유저 통계 업데이트 ─────────────────────────────────────
def update_streak():
    today = str(date.today())
    with get_db() as conn:
        row = conn.execute("SELECT last_study_date, streak FROM user_stats WHERE id=1").fetchone()
        last = row["last_study_date"]
        streak = row["streak"]
        if last == today:
            return streak
        from datetime import timedelta
        yesterday = str(date.today() - timedelta(days=1))
        new_streak = streak + 1 if last == yesterday else 1
        conn.execute(
            "UPDATE user_stats SET streak=?, last_study_date=? WHERE id=1",
            (new_streak, today)
        )
        return new_streak

# ── Pydantic 모델 ─────────────────────────────────────────
class AnswerRequest(BaseModel):
    word_id: int
    answer: str

class BookmarkRequest(BaseModel):
    word_id: int
    state: bool

# ── API 라우트 ─────────────────────────────────────────────
@app.get("/api/words")
def get_words(category: str = "all"):
    if category == "all":
        return WORDS
    return [w for w in WORDS if w["category"] == category]

@app.get("/api/words/{word_id}")
def get_word(word_id: int):
    w = WORDS_MAP.get(word_id)
    if not w:
        raise HTTPException(404, "단어를 찾을 수 없습니다")
    with get_db() as conn:
        prog = conn.execute(
            "SELECT * FROM word_progress WHERE word_id=?", (word_id,)
        ).fetchone()
    return {**w, "progress": dict(prog) if prog else {"correct": 0, "wrong": 0, "is_bookmarked": 0}}

@app.get("/api/quiz/next")
def next_quiz(category: str = "all"):
    pool = WORDS if category == "all" else [w for w in WORDS if w["category"] == category]
    if not pool:
        raise HTTPException(400, "해당 카테고리에 단어가 없습니다")

    with get_db() as conn:
        rows = conn.execute("SELECT word_id, correct, wrong FROM word_progress").fetchall()
    prog = {r["word_id"]: r for r in rows}

    # 틀린 단어 우선, 그다음 새 단어
    unseen = [w for w in pool if w["id"] not in prog]
    wrong_heavy = [w for w in pool if w["id"] in prog and prog[w["id"]]["wrong"] > prog[w["id"]]["correct"]]
    candidate = wrong_heavy or unseen or pool
    word = random.choice(candidate)

    # 오답 보기 3개 (같은 품사 우선)
    same_pos = [w for w in pool if w["pos"] == word["pos"] and w["id"] != word["id"]]
    other = [w for w in pool if w["id"] != word["id"] and w not in same_pos]
    distractors = random.sample(same_pos, min(3, len(same_pos))) + random.sample(other, max(0, 3 - min(3, len(same_pos))))
    distractors = distractors[:3]
    choices = [word["english"]] + [d["english"] for d in distractors]
    random.shuffle(choices)

    return {
        "word_id": word["id"],
        "korean": word["korean"],
        "pos": word["pos"],
        "sentence": word["sentence"],
        "sentence_ko": word["sentence_ko"],
        "sentence_blank": word["sentence"].replace(word["english"], "_" * len(word["english"]), 1),
        "hint": word["hint"],
        "choices": choices,
        "pronunciation": word["pronunciation"],
    }

@app.post("/api/quiz/answer")
def submit_answer(req: AnswerRequest):
    word = WORDS_MAP.get(req.word_id)
    if not word:
        raise HTTPException(404)

    correct = req.answer.strip().lower() == word["english"].lower()
    today = str(date.today())

    with get_db() as conn:
        conn.execute(
            """INSERT INTO word_progress (word_id, correct, wrong, last_seen)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(word_id) DO UPDATE SET
                 correct = correct + ?,
                 wrong   = wrong   + ?,
                 last_seen = ?""",
            (req.word_id, int(correct), int(not correct), today,
             int(correct), int(not correct), today)
        )
        conn.execute(
            """INSERT INTO daily_log (log_date, questions, correct)
               VALUES (?, 1, ?)
               ON CONFLICT(log_date) DO UPDATE SET
                 questions = questions + 1,
                 correct   = correct   + ?""",
            (today, int(correct), int(correct))
        )
        if correct:
            conn.execute("UPDATE user_stats SET diamonds=diamonds+1, xp=xp+10, total_correct=total_correct+1 WHERE id=1")
            # 리그 업그레이드
            row = conn.execute("SELECT xp FROM user_stats WHERE id=1").fetchone()
            xp = row["xp"]
            league = "bronze"
            if xp >= 2000: league = "diamond"
            elif xp >= 1000: league = "platinum"
            elif xp >= 500: league = "gold"
            elif xp >= 200: league = "silver"
            conn.execute("UPDATE user_stats SET league=? WHERE id=1", (league,))
        else:
            conn.execute("UPDATE user_stats SET total_wrong=total_wrong+1 WHERE id=1")

    streak = update_streak()
    with get_db() as conn:
        stats = dict(conn.execute("SELECT * FROM user_stats WHERE id=1").fetchone())

    return {
        "correct": correct,
        "correct_answer": word["english"],
        "pronunciation": word["pronunciation"],
        "sentence": word["sentence"],
        "sentence_ko": word["sentence_ko"],
        "diamonds": stats["diamonds"],
        "xp": stats["xp"],
        "streak": streak,
        "league": stats["league"],
    }

@app.get("/api/stats")
def get_stats():
    with get_db() as conn:
        stats = dict(conn.execute("SELECT * FROM user_stats WHERE id=1").fetchone())
        logs = conn.execute(
            "SELECT * FROM daily_log ORDER BY log_date DESC LIMIT 7"
        ).fetchall()
        progs = conn.execute("SELECT * FROM word_progress").fetchall()

    learned = sum(1 for p in progs if p["correct"] >= 3)
    accuracy = 0
    if stats["total_correct"] + stats["total_wrong"] > 0:
        accuracy = round(stats["total_correct"] / (stats["total_correct"] + stats["total_wrong"]) * 100)

    league_xp = {"bronze": 0, "silver": 200, "gold": 500, "platinum": 1000, "diamond": 2000}
    league_next = {"bronze": 200, "silver": 500, "gold": 1000, "platinum": 2000, "diamond": 9999}
    current_league = stats["league"]
    xp_min = league_xp.get(current_league, 0)
    xp_max = league_next.get(current_league, 9999)

    return {
        **stats,
        "total_words": len(WORDS),
        "learned_words": learned,
        "accuracy": accuracy,
        "weekly_log": [dict(l) for l in logs],
        "xp_min": xp_min,
        "xp_max": xp_max,
    }

@app.post("/api/bookmark")
def toggle_bookmark(req: BookmarkRequest):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO word_progress (word_id, is_bookmarked)
               VALUES (?, ?)
               ON CONFLICT(word_id) DO UPDATE SET is_bookmarked=?""",
            (req.word_id, int(req.state), int(req.state))
        )
    return {"ok": True}

@app.get("/api/bookmarks")
def get_bookmarks():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT word_id FROM word_progress WHERE is_bookmarked=1"
        ).fetchall()
    ids = {r["word_id"] for r in rows}
    return [w for w in WORDS if w["id"] in ids]

@app.get("/api/categories")
def get_categories():
    cats = sorted(set(w["category"] for w in WORDS))
    return cats

# ── GitHub 자동 배포 웹훅 ──────────────────────────────────
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "malhaeboka-secret")
REPO_DIR = BASE_DIR.parent  # Surver_test 루트

@app.post("/webhook/github")
async def github_webhook(request: Request, x_hub_signature_256: str = Header(None)):
    body = await request.body()

    # 서명 검증
    if x_hub_signature_256:
        expected = "sha256=" + hmac.new(
            WEBHOOK_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="서명 불일치")

    payload = json.loads(body)
    branch = payload.get("ref", "").replace("refs/heads/", "")
    pusher = payload.get("pusher", {}).get("name", "unknown")
    commits = len(payload.get("commits", []))

    # 배포 브랜치가 아니면 무시
    target_branch = os.environ.get("DEPLOY_BRANCH", "claude/malheboka-structure-analysis-GedwO")
    if branch != target_branch:
        return {"status": "skipped", "reason": f"branch {branch} is not deploy target"}

    # 비동기로 배포 실행
    deploy_script = str(BASE_DIR / "deploy.sh")
    subprocess.Popen(
        ["bash", deploy_script],
        cwd=str(REPO_DIR),
        stdout=open(str(BASE_DIR / "deploy.log"), "a"),
        stderr=subprocess.STDOUT,
    )

    return {
        "status": "deploying",
        "branch": branch,
        "pusher": pusher,
        "commits": commits,
    }

@app.get("/webhook/status")
def webhook_status():
    log_path = BASE_DIR / "deploy.log"
    lines = []
    if log_path.exists():
        with open(log_path) as f:
            lines = f.readlines()[-30:]
    return {"log": "".join(lines)}

# ── 정적 파일 ──────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(str(BASE_DIR / "static" / "index.html"))
