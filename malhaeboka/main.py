import json
import sqlite3
import random
import hmac
import hashlib
import subprocess
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "progress.db"
WORDS_PATH = BASE_DIR / "data" / "words.json"

app = FastAPI(title="말해보카")

# ── 업적 정의 ──────────────────────────────────────────────
ACHIEVEMENTS = {
    "first_correct": {"name": "첫 걸음", "desc": "첫 번째 정답!", "icon": "🎯"},
    "streak_3": {"name": "3일 연속", "desc": "3일 연속 학습 달성", "icon": "🔥"},
    "streak_7": {"name": "일주일!", "desc": "7일 연속 학습 달성", "icon": "🔥🔥"},
    "streak_30": {"name": "한 달!", "desc": "30일 연속 학습 달성", "icon": "🌟"},
    "diamonds_10": {"name": "다이아 수집가", "desc": "💎 10개 획득", "icon": "💎"},
    "diamonds_100": {"name": "다이아 부자", "desc": "💎 100개 획득", "icon": "💍"},
    "words_10": {"name": "초보 학습자", "desc": "단어 10개 완전 학습", "icon": "📚"},
    "words_30": {"name": "중급 학습자", "desc": "단어 30개 완전 학습", "icon": "📖"},
    "mastery_first": {"name": "첫 마스터", "desc": "단어 1개 완전 마스터 달성", "icon": "⭐"},
    "mastery_10": {"name": "마스터 학습자", "desc": "단어 10개 마스터", "icon": "🌠"},
    "placement_done": {"name": "레벨 측정 완료", "desc": "배치고사를 완료했습니다", "icon": "🎓"},
    "perfect_session": {"name": "퍼펙트!", "desc": "10문제 연속 정답", "icon": "🏆"},
    "league_silver": {"name": "실버 달성", "desc": "실버 리그 승급!", "icon": "🥈"},
    "league_gold": {"name": "골드 달성", "desc": "골드 리그 승급!", "icon": "🥇"},
}

# ── DB 초기화 ──────────────────────────────────────────────
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
            total_wrong INTEGER DEFAULT 0,
            hearts INTEGER DEFAULT 3,
            last_heart_regen TEXT DEFAULT '',
            consecutive_correct INTEGER DEFAULT 0,
            daily_goal INTEGER DEFAULT 10,
            today_new_words INTEGER DEFAULT 0,
            today_last_date TEXT DEFAULT ''
        );
        INSERT OR IGNORE INTO user_stats (id) VALUES (1);

        CREATE TABLE IF NOT EXISTS word_progress (
            word_id INTEGER PRIMARY KEY,
            correct INTEGER DEFAULT 0,
            wrong INTEGER DEFAULT 0,
            is_bookmarked INTEGER DEFAULT 0,
            last_seen TEXT DEFAULT '',
            next_review TEXT DEFAULT '',
            interval INTEGER DEFAULT 1,
            ease_factor REAL DEFAULT 2.5,
            repetitions INTEGER DEFAULT 0,
            mastery INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS daily_log (
            log_date TEXT PRIMARY KEY,
            questions INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS user_settings (
            id INTEGER PRIMARY KEY DEFAULT 1,
            daily_goal INTEGER DEFAULT 10,
            dark_mode INTEGER DEFAULT 0,
            user_level INTEGER DEFAULT 0,
            onboarded INTEGER DEFAULT 0,
            placement_done INTEGER DEFAULT 0
        );
        INSERT OR IGNORE INTO user_settings (id) VALUES (1);

        CREATE TABLE IF NOT EXISTS achievements (
            achievement_id TEXT PRIMARY KEY,
            unlocked_date TEXT
        );
        """)

init_db()

# ── 단어 로딩 ──────────────────────────────────────────────
def load_words():
    with open(WORDS_PATH, encoding="utf-8") as f:
        return json.load(f)

WORDS = load_words()
WORDS_MAP = {w["id"]: w for w in WORDS}

# ── SM-2 알고리즘 ──────────────────────────────────────────
def sm2_update(quality: int, repetitions: int, ease_factor: float, interval: int):
    """quality 0-5: 0=blackout, 3=correct hard, 4=correct, 5=perfect"""
    if quality < 3:
        repetitions = 0
        interval = 1  # 오답 → 내일 복습
    else:
        if repetitions == 0:
            interval = 3  # 첫 정답 → 3일 후
        elif repetitions == 1:
            interval = 7  # 두 번째 정답 → 1주일 후
        else:
            interval = round(interval * ease_factor)
        repetitions += 1
    ease_factor = max(1.3, ease_factor + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    return repetitions, ease_factor, interval

def calc_mastery(correct, wrong, interval, repetitions):
    if correct == 0 and wrong == 0:
        return 0
    if correct == 0:
        return 1
    ratio = correct / (correct + wrong)
    if interval >= 21 and ratio >= 0.8 and repetitions >= 5:
        return 5
    elif interval >= 14 and ratio >= 0.7 and repetitions >= 4:
        return 4
    elif interval >= 7 and ratio >= 0.6 and repetitions >= 3:
        return 3
    elif interval >= 3 and ratio >= 0.5:
        return 2
    else:
        return 1

# ── 스트릭 업데이트 ────────────────────────────────────────
def update_streak():
    today = str(date.today())
    with get_db() as conn:
        row = conn.execute("SELECT last_study_date, streak FROM user_stats WHERE id=1").fetchone()
        last = row["last_study_date"]
        streak = row["streak"]
        if last == today:
            return streak
        yesterday = str(date.today() - timedelta(days=1))
        new_streak = streak + 1 if last == yesterday else 1
        conn.execute(
            "UPDATE user_stats SET streak=?, last_study_date=? WHERE id=1",
            (new_streak, today)
        )
        return new_streak

# ── 하트 재생성 체크 ───────────────────────────────────────
def check_heart_regen(conn):
    row = conn.execute("SELECT hearts, last_heart_regen FROM user_stats WHERE id=1").fetchone()
    hearts = row["hearts"]
    last_regen = row["last_heart_regen"]
    if hearts >= 3:
        return hearts
    now = datetime.now()
    if last_regen:
        last_dt = datetime.fromisoformat(last_regen)
        minutes_elapsed = (now - last_dt).total_seconds() / 60
        hearts_to_add = int(minutes_elapsed // 30)
        if hearts_to_add > 0:
            new_hearts = min(3, hearts + hearts_to_add)
            conn.execute(
                "UPDATE user_stats SET hearts=?, last_heart_regen=? WHERE id=1",
                (new_hearts, now.isoformat())
            )
            return new_hearts
    else:
        conn.execute(
            "UPDATE user_stats SET last_heart_regen=? WHERE id=1",
            (now.isoformat(),)
        )
    return hearts

# ── 리그 계산 ──────────────────────────────────────────────
def calc_league(xp: int) -> str:
    if xp >= 2000:
        return "diamond"
    elif xp >= 1000:
        return "platinum"
    elif xp >= 500:
        return "gold"
    elif xp >= 200:
        return "silver"
    else:
        return "bronze"

# ── 업적 체크 ──────────────────────────────────────────────
def check_achievements(conn, stats, word_prog_list) -> list:
    today = str(date.today())
    new_achievements = []

    def unlock(achievement_id):
        existing = conn.execute(
            "SELECT achievement_id FROM achievements WHERE achievement_id=?",
            (achievement_id,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT OR IGNORE INTO achievements (achievement_id, unlocked_date) VALUES (?, ?)",
                (achievement_id, today)
            )
            ach = ACHIEVEMENTS.get(achievement_id, {})
            new_achievements.append({
                "id": achievement_id,
                "name": ach.get("name", ""),
                "desc": ach.get("desc", ""),
                "icon": ach.get("icon", ""),
            })

    total_correct = stats["total_correct"]
    diamonds = stats["diamonds"]
    streak = stats["streak"]
    consecutive_correct = stats["consecutive_correct"]
    league = stats["league"]

    if total_correct >= 1:
        unlock("first_correct")
    if streak >= 3:
        unlock("streak_3")
    if streak >= 7:
        unlock("streak_7")
    if streak >= 30:
        unlock("streak_30")
    if diamonds >= 10:
        unlock("diamonds_10")
    if diamonds >= 100:
        unlock("diamonds_100")
    if consecutive_correct >= 10:
        unlock("perfect_session")
    if league in ("silver", "gold", "platinum", "diamond"):
        unlock("league_silver")
    if league in ("gold", "platinum", "diamond"):
        unlock("league_gold")

    mastery_count = sum(1 for p in word_prog_list if p["mastery"] >= 5)
    learned_count = sum(1 for p in word_prog_list if p["mastery"] >= 3)

    if mastery_count >= 1:
        unlock("mastery_first")
    if mastery_count >= 10:
        unlock("mastery_10")
    if learned_count >= 10:
        unlock("words_10")
    if learned_count >= 30:
        unlock("words_30")

    return new_achievements

# ── Pydantic 모델 ──────────────────────────────────────────
class AnswerRequest(BaseModel):
    word_id: int
    answer: str
    mode: str = "keyboard"
    used_hint: bool = False

class BookmarkRequest(BaseModel):
    word_id: int
    state: bool

class SettingsRequest(BaseModel):
    daily_goal: Optional[int] = None
    dark_mode: Optional[int] = None
    user_level: Optional[int] = None
    onboarded: Optional[int] = None
    placement_done: Optional[int] = None

class PlacementSubmitRequest(BaseModel):
    answers: list

# ── API 라우트 ─────────────────────────────────────────────

@app.get("/api/stats")
def get_stats():
    with get_db() as conn:
        check_heart_regen(conn)
        stats = dict(conn.execute("SELECT * FROM user_stats WHERE id=1").fetchone())
        logs = conn.execute(
            "SELECT * FROM daily_log ORDER BY log_date DESC LIMIT 7"
        ).fetchall()
        progs = [dict(p) for p in conn.execute("SELECT * FROM word_progress").fetchall()]

    learned = sum(1 for p in progs if p["mastery"] >= 3)
    accuracy = 0
    if stats["total_correct"] + stats["total_wrong"] > 0:
        accuracy = round(
            stats["total_correct"] / (stats["total_correct"] + stats["total_wrong"]) * 100
        )

    league_xp = {"bronze": 0, "silver": 200, "gold": 500, "platinum": 1000, "diamond": 2000}
    league_next = {"bronze": 200, "silver": 500, "gold": 1000, "platinum": 2000, "diamond": 9999}
    current_league = stats["league"]
    xp_min = league_xp.get(current_league, 0)
    xp_max = league_next.get(current_league, 9999)

    # 카테고리별 통계
    all_categories = list(set(w["category"] for w in WORDS))
    prog_map = {p["word_id"]: p for p in progs}
    category_stats = {}
    for cat in all_categories:
        cat_words = [w for w in WORDS if w["category"] == cat]
        cat_ids = {w["id"] for w in cat_words}
        cat_learned = sum(1 for p in progs if p["word_id"] in cat_ids and p["mastery"] >= 3)
        category_stats[cat] = {"total": len(cat_words), "learned": cat_learned}

    # 마스터리 분포
    mastery_distribution = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    seen_ids = {p["word_id"] for p in progs}
    for p in progs:
        mastery_distribution[p["mastery"]] += 1
    unseen_count = len(WORDS) - len(seen_ids)
    mastery_distribution[0] += unseen_count

    return {
        **stats,
        "total_words": len(WORDS),
        "learned_words": learned,
        "accuracy": accuracy,
        "weekly_log": [dict(l) for l in logs],
        "xp_min": xp_min,
        "xp_max": xp_max,
        "category_stats": category_stats,
        "mastery_distribution": mastery_distribution,
    }

@app.get("/api/words")
def get_words(category: str = "all"):
    with get_db() as conn:
        progs = {
            p["word_id"]: dict(p)
            for p in conn.execute("SELECT * FROM word_progress").fetchall()
        }

    pool = WORDS if category == "all" else [w for w in WORDS if w["category"] == category]
    result = []
    for w in pool:
        prog = progs.get(w["id"], {"mastery": 0, "correct": 0, "wrong": 0, "is_bookmarked": 0})
        result.append({**w, "mastery": prog.get("mastery", 0)})
    return result

@app.get("/api/words/{word_id}")
def get_word(word_id: int):
    w = WORDS_MAP.get(word_id)
    if not w:
        raise HTTPException(404, "단어를 찾을 수 없습니다")
    with get_db() as conn:
        prog = conn.execute(
            "SELECT * FROM word_progress WHERE word_id=?", (word_id,)
        ).fetchone()
    prog_data = dict(prog) if prog else {
        "correct": 0, "wrong": 0, "is_bookmarked": 0,
        "mastery": 0, "repetitions": 0, "interval": 1,
        "ease_factor": 2.5, "next_review": "", "last_seen": ""
    }
    return {
        **w,
        "sentence2": w.get("sentence2", ""),
        "sentence2_ko": w.get("sentence2_ko", ""),
        "progress": prog_data
    }

@app.get("/api/quiz/next")
def next_quiz(category: str = "all"):
    with get_db() as conn:
        settings = dict(conn.execute("SELECT * FROM user_settings WHERE id=1").fetchone())
        hearts = check_heart_regen(conn)
        rows = conn.execute("SELECT * FROM word_progress").fetchall()

    if hearts <= 0:
        raise HTTPException(400, "하트가 없습니다. 30분 후에 재도전하세요.")

    prog = {r["word_id"]: dict(r) for r in rows}
    today = str(date.today())
    user_level = settings.get("user_level", 0)

    pool = WORDS if category == "all" else [w for w in WORDS if w["category"] == category]
    if not pool:
        raise HTTPException(400, "해당 카테고리에 단어가 없습니다")

    # 레벨 필터 (user_level==0 이면 모든 레벨)
    if user_level > 0:
        level_pool = [w for w in pool if w["level"] <= user_level + 1]
        if not level_pool:
            level_pool = pool
        pool = level_pool

    # 우선순위 1: next_review <= today (복습 예정)
    review_due = [
        w for w in pool
        if w["id"] in prog
        and prog[w["id"]]["next_review"]
        and prog[w["id"]]["next_review"] <= today
    ]

    # 우선순위 2: 아직 한 번도 보지 않은 새 단어
    unseen = [w for w in pool if w["id"] not in prog]

    # 우선순위 3: 오답이 많은 단어
    wrong_heavy = [
        w for w in pool
        if w["id"] in prog
        and prog[w["id"]]["wrong"] > prog[w["id"]]["correct"]
        and not (prog[w["id"]]["next_review"] and prog[w["id"]]["next_review"] <= today)
    ]

    if review_due:
        word = random.choice(review_due)
    elif unseen:
        word = random.choice(unseen)
    elif wrong_heavy:
        word = random.choice(wrong_heavy)
    else:
        word = random.choice(pool)

    # 오답 보기 3개 (같은 품사 우선)
    same_pos = [w for w in pool if w["pos"] == word["pos"] and w["id"] != word["id"]]
    other = [w for w in pool if w["id"] != word["id"] and w not in same_pos]
    distractors = (
        random.sample(same_pos, min(3, len(same_pos)))
        + random.sample(other, max(0, 3 - min(3, len(same_pos))))
    )
    distractors = distractors[:3]
    choices = [word["english"]] + [d["english"] for d in distractors]
    random.shuffle(choices)

    word_prog = prog.get(word["id"], {})
    return {
        "word_id": word["id"],
        "korean": word["korean"],
        "pos": word["pos"],
        "level": word["level"],
        "category": word["category"],
        "sentence": word["sentence"],
        "sentence_ko": word["sentence_ko"],
        "sentence_blank": word["sentence"].replace(word["english"], "_" * len(word["english"]), 1),
        "hint": word["hint"],
        "choices": choices,
        "pronunciation": word["pronunciation"],
        "mastery": word_prog.get("mastery", 0),
        "hearts": hearts,
    }

@app.post("/api/quiz/answer")
def submit_answer(req: AnswerRequest):
    word = WORDS_MAP.get(req.word_id)
    if not word:
        raise HTTPException(404, "단어를 찾을 수 없습니다")

    correct = req.answer.strip().lower() == word["english"].lower()
    today = str(date.today())
    now = datetime.now().isoformat()

    with get_db() as conn:
        hearts = check_heart_regen(conn)

        # SM-2 quality 매핑
        if correct:
            if req.mode == "voice":
                quality = 5
            elif req.mode == "keyboard" and not req.used_hint:
                quality = 5
            elif req.mode == "keyboard" and req.used_hint:
                quality = 4
            else:
                quality = 4
        else:
            quality = 1

        # 기존 진행 상황 가져오기
        existing = conn.execute(
            "SELECT * FROM word_progress WHERE word_id=?", (req.word_id,)
        ).fetchone()

        if existing:
            rep = existing["repetitions"]
            ef = existing["ease_factor"]
            iv = existing["interval"]
            new_correct = existing["correct"] + int(correct)
            new_wrong = existing["wrong"] + int(not correct)
        else:
            rep = 0
            ef = 2.5
            iv = 1
            new_correct = int(correct)
            new_wrong = int(not correct)

        new_rep, new_ef, new_iv = sm2_update(quality, rep, ef, iv)
        next_review_date = str(date.today() + timedelta(days=new_iv))
        new_mastery = calc_mastery(new_correct, new_wrong, new_iv, new_rep)

        conn.execute(
            """INSERT INTO word_progress
               (word_id, correct, wrong, last_seen, next_review, interval, ease_factor, repetitions, mastery)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(word_id) DO UPDATE SET
                 correct = ?,
                 wrong = ?,
                 last_seen = ?,
                 next_review = ?,
                 interval = ?,
                 ease_factor = ?,
                 repetitions = ?,
                 mastery = ?""",
            (
                req.word_id, new_correct, new_wrong, today,
                next_review_date, new_iv, new_ef, new_rep, new_mastery,
                new_correct, new_wrong, today,
                next_review_date, new_iv, new_ef, new_rep, new_mastery
            )
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
            conn.execute(
                "UPDATE user_stats SET diamonds=diamonds+1, xp=xp+10, total_correct=total_correct+1, "
                "consecutive_correct=consecutive_correct+1 WHERE id=1"
            )
        else:
            new_hearts = max(0, hearts - 1)
            conn.execute(
                "UPDATE user_stats SET total_wrong=total_wrong+1, consecutive_correct=0, "
                "hearts=?, last_heart_regen=? WHERE id=1",
                (new_hearts, now)
            )

        # 리그 업그레이드 체크
        row = conn.execute("SELECT xp FROM user_stats WHERE id=1").fetchone()
        new_league = calc_league(row["xp"])
        conn.execute("UPDATE user_stats SET league=? WHERE id=1", (new_league,))

        # 오늘 새 단어 카운트 업데이트
        stats_row = conn.execute("SELECT * FROM user_stats WHERE id=1").fetchone()
        today_last = stats_row["today_last_date"]
        today_new = stats_row["today_new_words"]
        if today_last != today:
            conn.execute(
                "UPDATE user_stats SET today_new_words=1, today_last_date=? WHERE id=1",
                (today,)
            )
        elif not existing:
            conn.execute(
                "UPDATE user_stats SET today_new_words=today_new_words+1 WHERE id=1"
            )

        stats = dict(conn.execute("SELECT * FROM user_stats WHERE id=1").fetchone())
        all_progs = [dict(p) for p in conn.execute("SELECT * FROM word_progress").fetchall()]
        new_achievements = check_achievements(conn, stats, all_progs)

    # 오답일 때 사용자가 선택한 단어의 한국어 뜻 찾기
    wrong_korean = ""
    if not correct:
        wrong_word = next((w for w in WORDS if w["english"].lower() == req.answer.strip().lower()), None)
        if wrong_word:
            wrong_korean = wrong_word["korean"]

    streak = update_streak()
    with get_db() as conn:
        stats = dict(conn.execute("SELECT * FROM user_stats WHERE id=1").fetchone())

    return {
        "correct": correct,
        "correct_answer": word["english"],
        "correct_korean": word["korean"],
        "pronunciation": word["pronunciation"],
        "sentence": word["sentence"],
        "sentence_ko": word["sentence_ko"],
        "sentence2": word.get("sentence2", ""),
        "sentence2_ko": word.get("sentence2_ko", ""),
        "wrong_answer": req.answer if not correct else "",
        "wrong_korean": wrong_korean,
        "diamonds": stats["diamonds"],
        "xp": stats["xp"],
        "streak": streak,
        "league": stats["league"],
        "hearts": stats["hearts"],
        "new_achievements": new_achievements,
        "mastery": new_mastery,
        "next_review": next_review_date,
    }

@app.get("/api/quiz/today")
def quiz_today():
    today = str(date.today())
    with get_db() as conn:
        settings = dict(conn.execute("SELECT * FROM user_settings WHERE id=1").fetchone())
        rows = conn.execute("SELECT * FROM word_progress").fetchall()
        log = conn.execute(
            "SELECT questions, correct FROM daily_log WHERE log_date=?", (today,)
        ).fetchone()
        stats_row = conn.execute("SELECT daily_goal FROM user_stats WHERE id=1").fetchone()

    prog = {r["word_id"]: dict(r) for r in rows}
    goal = settings.get("daily_goal", 10)

    review_due = sum(
        1 for p in prog.values()
        if p.get("next_review") and p["next_review"] <= today
    )
    new_available = sum(1 for w in WORDS if w["id"] not in prog)
    goal_progress = log["questions"] if log else 0

    return {
        "review_due": review_due,
        "new_available": new_available,
        "goal_progress": goal_progress,
        "goal": goal,
    }

@app.get("/api/placement/questions")
def placement_questions():
    questions = []
    for level in range(1, 6):
        level_words = [w for w in WORDS if w["level"] == level]
        selected = random.sample(level_words, min(4, len(level_words)))
        for word in selected:
            same_pos = [w for w in WORDS if w["pos"] == word["pos"] and w["id"] != word["id"]]
            other = [w for w in WORDS if w["id"] != word["id"] and w not in same_pos]
            distractors = (
                random.sample(same_pos, min(3, len(same_pos)))
                + random.sample(other, max(0, 3 - min(3, len(same_pos))))
            )
            distractors = distractors[:3]
            choices = [word["english"]] + [d["english"] for d in distractors]
            random.shuffle(choices)
            questions.append({
                "word_id": word["id"],
                "korean": word["korean"],
                "pos": word["pos"],
                "level": word["level"],
                "choices": choices,
                "correct": word["english"],
                "pronunciation": word["pronunciation"],
            })
    random.shuffle(questions)
    return questions[:20]

@app.post("/api/placement/submit")
def placement_submit(req: PlacementSubmitRequest):
    correct_by_level = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    total_by_level = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    for item in req.answers:
        word_id = item.get("word_id")
        answer = item.get("answer", "")
        word = WORDS_MAP.get(word_id)
        if not word:
            continue
        level = word["level"]
        total_by_level[level] = total_by_level.get(level, 0) + 1
        if answer.strip().lower() == word["english"].lower():
            correct_by_level[level] = correct_by_level.get(level, 0) + 1

    # 최고 레벨: 해당 레벨에서 50% 이상 정답
    user_level = 0
    for lvl in range(1, 6):
        total = total_by_level.get(lvl, 0)
        correct = correct_by_level.get(lvl, 0)
        if total > 0 and correct / total >= 0.5:
            user_level = lvl

    today = str(date.today())
    with get_db() as conn:
        conn.execute(
            "UPDATE user_settings SET user_level=?, placement_done=1 WHERE id=1",
            (user_level,)
        )
        conn.execute(
            "INSERT OR IGNORE INTO achievements (achievement_id, unlocked_date) VALUES (?, ?)",
            ("placement_done", today)
        )

    ach = ACHIEVEMENTS["placement_done"]
    return {
        "user_level": user_level,
        "correct_by_level": correct_by_level,
        "total_by_level": total_by_level,
        "new_achievement": {
            "id": "placement_done",
            "name": ach["name"],
            "desc": ach["desc"],
            "icon": ach["icon"],
        },
    }

@app.get("/api/user/settings")
def get_settings():
    with get_db() as conn:
        row = conn.execute("SELECT * FROM user_settings WHERE id=1").fetchone()
    return dict(row)

@app.post("/api/user/settings")
def update_settings(req: SettingsRequest):
    with get_db() as conn:
        existing = dict(conn.execute("SELECT * FROM user_settings WHERE id=1").fetchone())
        updates = {}
        if req.daily_goal is not None:
            updates["daily_goal"] = req.daily_goal
        if req.dark_mode is not None:
            updates["dark_mode"] = req.dark_mode
        if req.user_level is not None:
            updates["user_level"] = req.user_level
        if req.onboarded is not None:
            updates["onboarded"] = req.onboarded
        if req.placement_done is not None:
            updates["placement_done"] = req.placement_done
        if updates:
            set_clause = ", ".join(f"{k}=?" for k in updates)
            conn.execute(
                f"UPDATE user_settings SET {set_clause} WHERE id=1",
                list(updates.values())
            )
        row = conn.execute("SELECT * FROM user_settings WHERE id=1").fetchone()
    return dict(row)

@app.get("/api/achievements")
def get_achievements():
    with get_db() as conn:
        unlocked_rows = conn.execute("SELECT * FROM achievements").fetchall()
    unlocked = {r["achievement_id"]: r["unlocked_date"] for r in unlocked_rows}

    result = []
    for ach_id, ach_data in ACHIEVEMENTS.items():
        result.append({
            "id": ach_id,
            "name": ach_data["name"],
            "desc": ach_data["desc"],
            "icon": ach_data["icon"],
            "unlocked": ach_id in unlocked,
            "unlocked_date": unlocked.get(ach_id, None),
        })
    return result

@app.get("/api/word-of-day")
def word_of_day():
    today = str(date.today())
    day_hash = int(hashlib.md5(today.encode()).hexdigest(), 16)
    word = WORDS[day_hash % len(WORDS)]
    with get_db() as conn:
        prog = conn.execute(
            "SELECT * FROM word_progress WHERE word_id=?", (word["id"],)
        ).fetchone()
    prog_data = dict(prog) if prog else {"mastery": 0, "correct": 0, "wrong": 0}
    return {
        **word,
        "sentence2": word.get("sentence2", ""),
        "sentence2_ko": word.get("sentence2_ko", ""),
        "date": today,
        "mastery": prog_data.get("mastery", 0),
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
REPO_DIR = BASE_DIR.parent

@app.post("/webhook/github")
async def github_webhook(request: Request, x_hub_signature_256: str = Header(None)):
    body = await request.body()

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

    target_branch = os.environ.get("DEPLOY_BRANCH", "claude/malheboka-structure-analysis-GedwO")
    if branch != target_branch:
        return {"status": "skipped", "reason": f"branch {branch} is not deploy target"}

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
