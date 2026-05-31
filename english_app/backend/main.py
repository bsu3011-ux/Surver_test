from dotenv import load_dotenv
load_dotenv()

import os
import json
import re
import random
import sqlite3
import time
from datetime import date, datetime, timedelta
from typing import List, Optional

# 히라가나·가타카나·CJK 한자(간체/번체/일본어) 탐지
_CJK_RE = re.compile(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')

def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ''))

def _strip_cjk(text: str) -> str:
    return _CJK_RE.sub('', text or '').strip()

def _clean_words(words: list) -> list:
    """Korean 필드에 남은 CJK 문자를 강제 제거한다."""
    for w in words:
        for field in ('korean', 'example_ko', 'tip'):
            if _has_cjk(w.get(field, '')):
                w[field] = _strip_cjk(w[field])
    return words

def _words_have_cjk(words: list) -> bool:
    return any(
        _has_cjk(w.get(f, ''))
        for w in words
        for f in ('korean', 'example_ko', 'tip')
    )

from groq import Groq
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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
    "daily":            "일상 대화 (Daily Life) - greetings, hobbies, weather, everyday activities",
    "travel":           "여행 (Travel) - hotel booking, directions, restaurants, sightseeing",
    "business":         "비즈니스 (Business) - emails, meetings, presentations, negotiations",
    "interview":        "취업 면접 (Job Interview) - self-introduction, strengths/weaknesses, career goals",
    # TOEIC Speaking 전용
    "toeic_picture":    "TOEIC Speaking Part 1 — 사진 묘사 (Picture Description). 직장·야외·일상 사진을 묘사하는 연습. 현재진행형, 위치 표현, 상태 묘사 중심",
    "toeic_opinion":    "TOEIC Speaking Part 5 — 의견 표현 (Express an Opinion). 찬반 주제에 대해 이유 2가지를 들어 자신의 의견을 논리적으로 말하는 연습",
    "toeic_solution":   "TOEIC Speaking Part 4 — 문제 해결 (Propose a Solution). 불만·문제 상황의 음성 메시지를 듣고 해결책을 제안하는 연습",
    "toeic_respond":    "TOEIC Speaking Part 3 — 질문 응답 (Respond to Questions). 인터뷰·설문 형식으로 자연스럽게 답변하는 연습",
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


class LearningModeUpdate(BaseModel):
    learning_mode: str  # 'general' | 'toeic_speaking'


@app.post("/api/profile/learning-mode")
def update_learning_mode(body: LearningModeUpdate):
    allowed = {"general", "toeic_speaking"}
    if body.learning_mode not in allowed:
        raise HTTPException(status_code=400, detail="잘못된 학습 모드입니다.")
    profile = get_profile()
    if not profile:
        raise HTTPException(status_code=400, detail="프로필이 없습니다.")
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE user_profile SET learning_mode = ? WHERE id = 1",
            (body.learning_mode,),
        )
        conn.commit()
    finally:
        conn.close()
    return {"learning_mode": body.learning_mode}


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

        if rows and len(rows) >= daily_count:
            return {
                "date": today,
                "level_code": level_code,
                "level_label": level_label,
                "words": [dict(r) for r in rows],
            }

        # 단어 수 부족하면 기존 오늘 단어 삭제 후 재생성
        if rows:
            conn.execute(
                "DELETE FROM vocab_words WHERE created_date = ? AND level_code = ?",
                (today, level_code),
            )
            conn.commit()

        # Generate with Groq
        learning_mode = profile.get("learning_mode", "general")
        groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

        LEVEL_VOCAB_GUIDE = {
            "A2": "elementary vocabulary (greet, family, simple verbs). Avoid overly basic words like go/eat/water.",
            "B1": "pre-intermediate vocabulary (demonstrate, various, arrange, prefer, involve).",
            "B2": "intermediate vocabulary (ambiguous, inevitable, substantial, persuade, elaborate). NEVER use basic words like cloud/house/run.",
            "C1": "upper-intermediate vocabulary (eloquent, meticulous, compelling, nuance, rhetoric).",
            "C2": "advanced/near-native vocabulary (juxtapose, quintessential, perspicacious, ephemeral).",
        }
        level_guide = LEVEL_VOCAB_GUIDE.get(level_code, LEVEL_VOCAB_GUIDE["B1"])

        EXAMPLE_JSON = '''[{"type":"word","english":"inevitable","pronunciation":"/ɪnˈevɪtəbl/","korean":"불가피한","part_of_speech":"adjective","example_en":"Change is inevitable in life.","example_ko":"변화는 삶에서 불가피하다.","tip":"in(아닌)+evit(피하다) = 피할 수 없는"}]'''

        if learning_mode == "toeic_speaking":
            mode_instruction = f"""You are an expert English vocabulary teacher. Select {daily_count} TOEIC Speaking vocabulary items for a Korean learner.
Categories (mix evenly): business verbs (propose, negotiate, allocate, coordinate), logical connectors (furthermore, consequently, nevertheless), descriptive phrases (adjacent to, in the foreground, appears to be), formal expressions (It would be advisable to, regarding, pertaining to), problem-solving words (alternative, feasible, contingency, mitigation).
All example sentences must be business/workplace situations."""
        else:
            mode_instruction = f"""You are an expert English vocabulary teacher. Select {daily_count} vocabulary items (70% words, 30% idioms) for a Korean learner at CEFR level {level_code}.
Level {level_code} means: {level_guide}
Vary the selection using today's date {date.today().isoformat()} as a seed. Each day must have DIFFERENT words."""

        def build_prompt(n, exclude=None):
            excl = f"\nDo NOT include any of these already-selected words: {', '.join(exclude)}." if exclude else ""
            return f"""{mode_instruction}
{excl}
Select exactly {n} items. Return ONLY a valid JSON array — no markdown, no code fences, no explanation.
Each object must have exactly these fields: type ("word" or "idiom"), english, pronunciation (IPA in /slashes/), korean, part_of_speech, example_en, example_ko, tip.
CRITICAL RULES — STRICTLY ENFORCED:
- korean: Korean meaning in PURE HANGUL ONLY. Absolutely NO Chinese characters (漢字), NO Japanese characters (漢字/ひらがな/カタカナ). Write natural Korean like: "같은 생각을 가진", "흠잡을 데 없는", "모호한", "미루다".
- example_ko: Pure Korean sentence. NO CJK characters at all. Translate example_en accurately.
- tip: Korean only, or "" if no helpful tip.
❌ WRONG examples (CJK contamination — NEVER output these): "마이너스一点도 없는", "同じ 생각을 가진", "徐々に"
✅ CORRECT examples: "흠잡을 데 없는", "같은 생각을 가진", "서서히"

Example of correct output format:
{EXAMPLE_JSON}"""

        def _parse_raw(raw: str) -> list:
            raw = raw.strip()
            if raw.startswith("```"):
                raw = "\n".join(l for l in raw.split("\n") if not l.startswith("```")).strip()
            return json.loads(raw)

        def call_groq(prompt_text):
            # CJK 감지 시 1회 자동 재시도, 그래도 남으면 강제 제거
            for attempt in range(2):
                resp = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt_text}],
                    max_tokens=2000,
                )
                result = _parse_raw(resp.choices[0].message.content)
                if not _words_have_cjk(result):
                    return result
                if attempt == 0:
                    time.sleep(3)  # 짧게 대기 후 재시도
            # 재시도 후에도 CJK 남아 있으면 강제 제거
            return _clean_words(result)

        # 10개씩 나눠서 요청 (llama-3.3-70b-versatile: 6000 TPM → sleep 12s between batches)
        batch = 10
        words_data = []
        remaining = daily_count
        while remaining > 0:
            n = min(batch, remaining)
            used = [w.get("english", "") for w in words_data]
            try:
                chunk = call_groq(build_prompt(n, exclude=used if used else None))
                words_data += chunk
                remaining -= len(chunk)
            except Exception as e:
                if words_data:
                    break  # 일부라도 있으면 진행
                raise
            if remaining > 0:
                time.sleep(12)

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


@app.get("/api/vocab/stats")
def get_vocab_stats():
    profile = get_profile()
    if not profile:
        raise HTTPException(status_code=400, detail="프로필이 없습니다.")

    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT id, english, pronunciation, korean, part_of_speech,
                   example_en, example_ko, type, review_count, correct_count, created_date
            FROM vocab_words WHERE level_code = ?
            ORDER BY
                CASE WHEN review_count = 0 THEN 2
                     WHEN CAST(correct_count AS FLOAT) / review_count < 0.6 THEN 0
                     ELSE 1 END ASC,
                CAST(correct_count AS FLOAT) / (review_count + 0.01) ASC
        """, (profile["level_code"],)).fetchall()
    finally:
        conn.close()

    words = []
    for row in rows:
        d = dict(row)
        d["accuracy"] = round(d["correct_count"] / d["review_count"] * 100) if d["review_count"] > 0 else None
        words.append(d)

    reviewed = [w for w in words if w["accuracy"] is not None]
    wrong_count = sum(1 for w in reviewed if w["accuracy"] < 60)
    avg_accuracy = round(sum(w["accuracy"] for w in reviewed) / len(reviewed)) if reviewed else None

    return {
        "words": words,
        "wrong_count": wrong_count,
        "total_reviewed": len(reviewed),
        "avg_accuracy": avg_accuracy,
    }


@app.get("/api/quiz/questions")
def get_quiz_questions(mode: str = "random"):
    """mode: 'random' (기본, 오답 우선 혼합) | 'review' (오답 단어만)"""
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

    def accuracy(w):
        return w["correct_count"] / w["review_count"] if w["review_count"] > 0 else None

    wrong_words = [w for w in words if accuracy(w) is not None and accuracy(w) < 0.7]
    other_words = [w for w in words if w not in wrong_words]

    if mode == "review":
        if len(wrong_words) < 4:
            return {"error": f"오답 단어가 {len(wrong_words)}개뿐입니다. 퀴즈를 더 풀어 오답을 쌓아보세요!", "wrong_count": len(wrong_words)}
        pool = wrong_words
    else:
        # 오답 최대 6개 + 나머지 랜덤으로 10개 채우기
        n_wrong = min(len(wrong_words), 6)
        n_other = min(len(other_words), 10 - n_wrong)
        pool = (random.sample(wrong_words, n_wrong) if n_wrong else []) + \
               (random.sample(other_words, n_other) if n_other else [])
        if len(pool) < 4:
            return {"error": "단어가 부족합니다. 더 많은 단어를 학습해 주세요."}
        random.shuffle(pool)

    sample_size = min(10, len(pool))
    sampled = random.sample(pool, sample_size)

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

    system_prompt = f"""You are an English speaking coach for a Korean learner.
Level: {body.level_code} — {level_guidance}
Topic: {topic_desc}

For every user message, do three things:
1. REPLY naturally in English (2-3 sentences, conversational tone).
2. GRAMMAR CHECK: detect any grammar, vocabulary, or expression error in the user's last message.
3. PRONUNCIATION TIP: pick up to 2 words from the user's last message that Korean speakers commonly mispronounce (focus on: th/f/v sounds, r vs l, word stress, vowel length, silent letters). Only flag words the user actually wrote. Skip if no notable issues.

Return ONLY valid JSON — no markdown, no explanation outside JSON:
{{"reply":"...","correction":{{"has_error":false,"original":null,"corrected":null,"explanation":null}},"pronunciation":{{"has_tip":false,"words":[]}}}}

Grammar error example:
{{"reply":"...","correction":{{"has_error":true,"original":"I am very interest in","corrected":"I am very interested in","explanation":"감정 형용사는 -ed형: interested (관심 있는)"}},"pronunciation":{{"has_tip":false,"words":[]}}}}

Pronunciation tip example:
{{"reply":"...","correction":{{"has_error":false,"original":null,"corrected":null,"explanation":null}},"pronunciation":{{"has_tip":true,"words":[{{"word":"thoroughly","ipa":"/ˈθʌr.ə.li/","tip":"th는 혀끝을 윗니에 살짝 대고 바람 — '덜리'가 아닌 'θʌrəli'"}}]}}}}"""

    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    messages = [{"role": "system", "content": system_prompt}]
    messages += [{"role": m.role, "content": m.content} for m in body.messages]

    empty_pronunciation = {"has_tip": False, "words": []}
    empty_correction = {"has_error": False, "original": None, "corrected": None, "explanation": None}

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=1024,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = "\n".join(l for l in raw.split("\n") if not l.startswith("```")).strip()

        parsed = json.loads(raw)
        # 누락 필드 보완
        parsed.setdefault("correction", empty_correction)
        parsed.setdefault("pronunciation", empty_pronunciation)
        return parsed
    except json.JSONDecodeError:
        return {
            "reply": raw if "raw" in locals() else "Sorry, I couldn't generate a response.",
            "correction": empty_correction,
            "pronunciation": empty_pronunciation,
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


# ── 빌드된 프론트엔드 정적 파일 서빙 ─────────────────────────────────
from pathlib import Path

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


@app.get("/assets/{file_path:path}")
def serve_asset(file_path: str):
    asset = FRONTEND_DIST / "assets" / file_path
    if asset.exists() and asset.is_file():
        return FileResponse(str(asset))
    raise HTTPException(status_code=404, detail="Asset not found")


@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    if full_path:
        candidate = FRONTEND_DIST / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    raise HTTPException(status_code=404, detail="Frontend not built. Run: cd frontend && npm run build")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
