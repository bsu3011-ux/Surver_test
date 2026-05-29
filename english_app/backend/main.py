from dotenv import load_dotenv
load_dotenv()

import os
import json
import random
import sqlite3
from datetime import date, datetime, timedelta
from typing import List, Optional

import anthropic
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import get_conn, init_db
from level_data import QUESTIONS, LEVEL_MAP, VOCAB_COUNTS

app = FastAPI(title="English Learning App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    init_db()


TOPICS = {
    "daily": "일상 대화 (Daily Life) - greetings, hobbies, weather, everyday activities",
    "travel": "여행 (Travel) - hotel booking, directions, restaurants, sightseeing",
    "business": "비즈니스 (Business) - emails, meetings, presentations, negotiations",
    "interview": "취업 면접 (Job Interview) - self-introduction, strengths/weaknesses, career goals",
}

LEVEL_GUIDANCE = {
    "A2": "Use very simple sentences and common vocabulary only.",
    "B1": "Use everyday sentences, not too complex.",
    "B2": "Use varied sentence structures and some idiomatic expressions.",
    "C1": "Use advanced vocabulary, idioms, and nuanced expressions.",
    "C2": "Converse like a native speaker with rich vocabulary.",
}


def get_level_info(score: int):
    for lo, hi, code, label in LEVEL_MAP:
        if lo <= score <= hi:
            return code, label
    return "A2", "초급 (Beginner)"


def get_profile():
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


# ─── Models ──────────────────────────────────────────────────────────────────

class LevelTestSubmit(BaseModel):
    answers: List[int]


class VocabMark(BaseModel):
    word_id: int
    correct: bool


class QuizResult(BaseModel):
    word_id: int
    correct: bool


class QuizSubmit(BaseModel):
    results: List[QuizResult]


class ConversationMessage(BaseModel):
    role: str
    content: str


class ConversationRequest(BaseModel):
    messages: List[ConversationMessage]
    topic: str
    level_code: str


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/api/profile")
def get_profile_route():
    profile = get_profile()
    if profile:
        return {**profile, "exists": True}
    return {"exists": False}


@app.get("/api/level-test/questions")
def get_questions():
    result = []
    for i, q in enumerate(QUESTIONS):
        result.append({
            "id": i + 1,
            "question": q["question"],
            "options": q["options"],
            "level": q["level"],
        })
    return result


@app.post("/api/level-test/submit")
def submit_level_test(body: LevelTestSubmit):
    if len(body.answers) != len(QUESTIONS):
        raise HTTPException(status_code=400, detail="답변 수가 맞지 않습니다.")

    score = 0
    for i, ans in enumerate(body.answers):
        if ans == QUESTIONS[i]["answer"]:
            score += 1

    level_code, level_label = get_level_info(score)
    daily_vocab_count = VOCAB_COUNTS[level_code]
    assessed_at = datetime.now().isoformat()

    conn = get_conn()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO user_profile
               (id, level_code, level_label, score, total, assessed_at, daily_vocab_count)
               VALUES (1, ?, ?, ?, ?, ?, ?)""",
            (level_code, level_label, score, len(QUESTIONS), assessed_at, daily_vocab_count),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "score": score,
        "total": len(QUESTIONS),
        "level_code": level_code,
        "level_label": level_label,
        "daily_vocab_count": daily_vocab_count,
    }


@app.get("/api/vocab/today")
def get_today_vocab():
    profile = get_profile()
    if not profile:
        raise HTTPException(status_code=400, detail="프로필이 없습니다. 레벨 테스트를 먼저 해주세요.")

    today = date.today().isoformat()
    level_code = profile["level_code"]
    level_label = profile["level_label"]
    daily_count = profile["daily_vocab_count"]

    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM vocab_words WHERE created_date = ? AND level_code = ? ORDER BY id",
            (today, level_code),
        ).fetchall()

        if rows:
            return {
                "date": today,
                "level_code": level_code,
                "level_label": level_label,
                "words": [dict(r) for r in rows],
            }

        # Generate with Claude
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        prompt = f"""Generate {daily_count} English vocabulary items for a Korean learner at level {level_code}.
Mix words and idioms (about 70% words, 30% idioms).

Return ONLY a JSON array (no markdown, no code fences) with exactly {daily_count} items.
Each item must have these fields:
- type: "word" or "idiom"
- english: the word or idiom
- pronunciation: phonetic pronunciation (e.g. /prəˌnʌnsiˈeɪʃən/)
- korean: Korean translation/meaning
- part_of_speech: e.g. "noun", "verb", "adjective", "idiom", etc.
- example_en: an example sentence in English
- example_ko: Korean translation of the example sentence
- tip: a brief memory tip or usage note in Korean (can be empty string if none)

Return only the JSON array, nothing else."""

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            # Remove first and last lines if they are code fences
            lines = [l for l in lines if not l.startswith("```")]
            raw = "\n".join(lines).strip()

        words_data = json.loads(raw)

        for w in words_data:
            conn.execute(
                """INSERT INTO vocab_words
                   (english, pronunciation, korean, part_of_speech, example_en, example_ko, tip, type, level_code, created_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    w.get("english", ""),
                    w.get("pronunciation", ""),
                    w.get("korean", ""),
                    w.get("part_of_speech", ""),
                    w.get("example_en", ""),
                    w.get("example_ko", ""),
                    w.get("tip", ""),
                    w.get("type", "word"),
                    level_code,
                    today,
                ),
            )

        conn.execute("INSERT OR IGNORE INTO study_days (date) VALUES (?)", (today,))
        conn.commit()

        rows = conn.execute(
            "SELECT * FROM vocab_words WHERE created_date = ? AND level_code = ? ORDER BY id",
            (today, level_code),
        ).fetchall()

        return {
            "date": today,
            "level_code": level_code,
            "level_label": level_label,
            "words": [dict(r) for r in rows],
        }
    finally:
        conn.close()


@app.get("/api/vocab/library")
def get_vocab_library():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM vocab_words ORDER BY created_date DESC, id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.post("/api/vocab/mark")
def mark_vocab(body: VocabMark):
    conn = get_conn()
    try:
        if body.correct:
            conn.execute(
                "UPDATE vocab_words SET review_count = review_count + 1, correct_count = correct_count + 1 WHERE id = ?",
                (body.word_id,),
            )
        else:
            conn.execute(
                "UPDATE vocab_words SET review_count = review_count + 1 WHERE id = ?",
                (body.word_id,),
            )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/quiz/questions")
def get_quiz_questions():
    profile = get_profile()
    if not profile:
        raise HTTPException(status_code=400, detail="프로필이 없습니다.")

    level_code = profile["level_code"]

    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM vocab_words WHERE level_code = ?",
            (level_code,),
        ).fetchall()
        words = [dict(r) for r in rows]
    finally:
        conn.close()

    if len(words) < 4:
        return {"error": "단어가 부족합니다. 더 많은 단어를 학습해 주세요."}

    # Generate up to 10 questions: 50% meaning, 50% english
    sample_size = min(10, len(words))
    sampled = random.sample(words, sample_size)

    questions = []
    for i, word in enumerate(sampled):
        q_type = "meaning" if i % 2 == 0 else "english"

        # Get 3 wrong options from other words
        other_words = [w for w in words if w["id"] != word["id"]]
        wrong_picks = random.sample(other_words, min(3, len(other_words)))

        if q_type == "meaning":
            # Show english, pick Korean answer
            correct_answer = word["korean"]
            wrong_options = [w["korean"] for w in wrong_picks]
            question_text = f"'{word['english']}'의 뜻은?"
        else:
            # Show korean, pick English answer
            correct_answer = word["english"]
            wrong_options = [w["english"] for w in wrong_picks]
            question_text = f"'{word['korean']}'를 영어로?"

        # Build options list and shuffle
        options = wrong_options[:3] + [correct_answer]
        random.shuffle(options)
        correct_index = options.index(correct_answer)

        questions.append({
            "word_id": word["id"],
            "type": q_type,
            "question": question_text,
            "options": options,
            "correct_index": correct_index,
        })

    return {"questions": questions}


@app.post("/api/quiz/submit")
def submit_quiz(body: QuizSubmit):
    profile = get_profile()
    if not profile:
        raise HTTPException(status_code=400, detail="프로필이 없습니다.")

    level_code = profile["level_code"]
    today = date.today().isoformat()
    correct_count = 0
    total_count = len(body.results)

    conn = get_conn()
    try:
        for r in body.results:
            if r.correct:
                correct_count += 1
                conn.execute(
                    "UPDATE vocab_words SET review_count = review_count + 1, correct_count = correct_count + 1 WHERE id = ?",
                    (r.word_id,),
                )
            else:
                conn.execute(
                    "UPDATE vocab_words SET review_count = review_count + 1 WHERE id = ?",
                    (r.word_id,),
                )

        conn.execute(
            "INSERT INTO quiz_sessions (date, correct, total, level_code) VALUES (?, ?, ?, ?)",
            (today, correct_count, total_count, level_code),
        )
        conn.execute("INSERT OR IGNORE INTO study_days (date) VALUES (?)", (today,))
        conn.commit()
    finally:
        conn.close()

    accuracy_pct = round((correct_count / total_count * 100) if total_count > 0 else 0, 1)

    return {
        "correct": correct_count,
        "total": total_count,
        "accuracy_pct": accuracy_pct,
    }


@app.post("/api/conversation/message")
def conversation_message(body: ConversationRequest):
    topic_desc = TOPICS.get(body.topic, TOPICS["daily"])
    level_guidance = LEVEL_GUIDANCE.get(body.level_code, LEVEL_GUIDANCE["B1"])

    system_prompt = f"""You are an English conversation partner for a Korean learner.
Level: {body.level_code} — {level_guidance}
Topic: {topic_desc}

Rules:
1. Respond naturally in English (2-4 sentences max)
2. Check the user's LAST message for grammar/spelling errors
3. Return ONLY a JSON object with this exact structure:
{{"reply": "Your English response", "correction": {{"has_error": false, "original": null, "corrected": null, "explanation": null}}}}

If there is an error:
{{"reply": "Your English response", "correction": {{"has_error": true, "original": "what they wrote incorrectly", "corrected": "the correct version", "explanation": "한국어로 간단히 설명"}}}}"""

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )
        raw = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            raw = "\n".join(lines).strip()

        parsed = json.loads(raw)
        return parsed
    except json.JSONDecodeError:
        return {
            "reply": raw if "raw" in dir() else "Sorry, I couldn't generate a response.",
            "correction": {
                "has_error": False,
                "original": None,
                "corrected": None,
                "explanation": None,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard")
def get_dashboard():
    profile = get_profile()
    if not profile:
        raise HTTPException(status_code=400, detail="프로필이 없습니다.")

    conn = get_conn()
    try:
        total_words = conn.execute("SELECT COUNT(*) FROM vocab_words WHERE level_code = ?", (profile["level_code"],)).fetchone()[0]
        quiz_sessions_count = conn.execute("SELECT COUNT(*) FROM quiz_sessions WHERE level_code = ?", (profile["level_code"],)).fetchone()[0]

        avg_row = conn.execute(
            "SELECT AVG(CAST(correct AS REAL) / CAST(total AS REAL) * 100) FROM quiz_sessions WHERE level_code = ? AND total > 0",
            (profile["level_code"],),
        ).fetchone()[0]
        avg_accuracy = round(avg_row, 1) if avg_row is not None else 0.0

        # Calculate streak: consecutive days ending today or yesterday
        study_dates = conn.execute(
            "SELECT date FROM study_days ORDER BY date DESC"
        ).fetchall()
        study_dates = [r[0] for r in study_dates]

        streak = 0
        if study_dates:
            today = date.today()
            check_date = today
            # Allow streak if studied today or yesterday
            if study_dates[0] == today.isoformat():
                check_date = today
            elif study_dates[0] == (today - timedelta(days=1)).isoformat():
                check_date = today - timedelta(days=1)
            else:
                check_date = None

            if check_date is not None:
                for d_str in study_dates:
                    if d_str == check_date.isoformat():
                        streak += 1
                        check_date = check_date - timedelta(days=1)
                    else:
                        break

    finally:
        conn.close()

    return {
        "level_code": profile["level_code"],
        "level_label": profile["level_label"],
        "total_words": total_words,
        "quiz_sessions": quiz_sessions_count,
        "avg_accuracy": avg_accuracy,
        "streak_days": streak,
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
