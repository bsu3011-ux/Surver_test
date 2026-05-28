QUESTIONS = [
    # ── 초급 (1~5번) ─────────────────────────────────────────────
    {
        "level": "easy",
        "question": "1. 빈칸에 알맞은 것을 고르세요.\n   \"She ___ to school every day.\"",
        "options": ["go", "goes", "going", "gone"],
        "answer": 1,
        "explanation": "3인칭 단수 현재형: She goes",
    },
    {
        "level": "easy",
        "question": "2. 'delicious'의 뜻은?",
        "options": ["맛있는", "빠른", "슬픈", "어려운"],
        "answer": 0,
        "explanation": "delicious = 맛있는",
    },
    {
        "level": "easy",
        "question": "3. 올바른 문장을 고르세요.",
        "options": [
            "He don't like coffee.",
            "He doesn't like coffee.",
            "He not like coffee.",
            "He do not likes coffee.",
        ],
        "answer": 1,
        "explanation": "3인칭 단수 부정문: doesn't + 동사원형",
    },
    {
        "level": "easy",
        "question": "4. 'communicate'의 뜻은?",
        "options": ["여행하다", "소통하다", "계산하다", "기억하다"],
        "answer": 1,
        "explanation": "communicate = 소통하다, 의사소통하다",
    },
    {
        "level": "easy",
        "question": "5. 빈칸에 알맞은 것을 고르세요.\n   \"I ___ been waiting for an hour.\"",
        "options": ["have", "has", "had", "having"],
        "answer": 0,
        "explanation": "주어가 I이므로 현재완료: I have been",
    },
    # ── 중급 (6~10번) ────────────────────────────────────────────
    {
        "level": "medium",
        "question": "6. 'procrastinate'의 뜻은?",
        "options": ["서두르다", "미루다", "계획하다", "완성하다"],
        "answer": 1,
        "explanation": "procrastinate = (해야 할 일을) 미루다",
    },
    {
        "level": "medium",
        "question": "7. 올바른 가정법 문장을 고르세요.",
        "options": [
            "If I would have money, I could buy it.",
            "If I had money, I could buy it.",
            "If I have money, I can bought it.",
            "If I had money, I can buy it.",
        ],
        "answer": 1,
        "explanation": "가정법 과거: If + 주어 + 과거형, 주어 + could/would + 동사원형",
    },
    {
        "level": "medium",
        "question": "8. 숙어 'bite the bullet'의 뜻은?",
        "options": [
            "총을 쏘다",
            "힘든 상황을 참고 견디다",
            "빨리 달리다",
            "음식을 서둘러 먹다",
        ],
        "answer": 1,
        "explanation": "bite the bullet = 이를 악물고 참다, 힘든 일을 기꺼이 하다",
    },
    {
        "level": "medium",
        "question": "9. 'ambiguous'의 뜻은?",
        "options": ["명확한", "모호한/불분명한", "아름다운", "위험한"],
        "answer": 1,
        "explanation": "ambiguous = 모호한, 두 가지로 해석될 수 있는",
    },
    {
        "level": "medium",
        "question": "10. 빈칸에 알맞은 것을 고르세요.\n    \"By the time she arrived, he ___ already left.\"",
        "options": ["has", "had", "have", "having"],
        "answer": 1,
        "explanation": "과거완료(대과거): 과거보다 더 이전 동작 → had + p.p.",
    },
    # ── 고급 (11~15번) ───────────────────────────────────────────
    {
        "level": "hard",
        "question": "11. 'ephemeral'의 뜻은?",
        "options": ["영원한", "일시적인/덧없는", "강렬한", "투명한"],
        "answer": 1,
        "explanation": "ephemeral = 수명이 짧은, 일시적인 (ex. ephemeral beauty)",
    },
    {
        "level": "hard",
        "question": "12. 빈칸에 알맞은 것을 고르세요 (가정법).\n    \"I wish I ___ fluent in English.\"",
        "options": ["am", "was", "were", "being"],
        "answer": 2,
        "explanation": "I wish + 가정법 과거: were (주어에 관계없이 were 사용)",
    },
    {
        "level": "hard",
        "question": "13. 숙어 'the elephant in the room'의 뜻은?",
        "options": [
            "매우 큰 장애물",
            "모두가 알지만 아무도 언급하지 않는 불편한 문제",
            "파티의 주인공",
            "눈에 띄는 특이한 손님",
        ],
        "answer": 1,
        "explanation": "the elephant in the room = 존재하지만 모두가 외면하는 명백한 문제",
    },
    {
        "level": "hard",
        "question": "14. 'juxtapose'의 뜻은?",
        "options": ["나란히 놓다/대비시키다", "파괴하다", "축하하다", "숨기다"],
        "answer": 0,
        "explanation": "juxtapose = 두 가지를 나란히 놓아 비교·대조하다",
    },
    {
        "level": "hard",
        "question": "15. 빈칸에 가장 어울리는 단어를 고르세요.\n    \"The scientist's findings were ___, overturning decades of established theory.\"",
        "options": ["mundane", "groundbreaking", "trivial", "ambivalent"],
        "answer": 1,
        "explanation": "groundbreaking = 획기적인 / mundane=평범한, trivial=사소한, ambivalent=양가감정의",
    },
]

LEVEL_MAP = [
    (0,  5,  "A2", "초급 (Beginner)"),
    (6,  8,  "B1", "초중급 (Elementary)"),
    (9,  11, "B2", "중급 (Intermediate)"),
    (12, 13, "C1", "중상급 (Upper-Intermediate)"),
    (14, 15, "C2", "고급 (Advanced)"),
]

VOCAB_COUNTS = {
    "A2": 5,
    "B1": 7,
    "B2": 8,
    "C1": 10,
    "C2": 10,
}
