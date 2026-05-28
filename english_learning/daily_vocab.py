"""
매일 영어 단어/숙어를 Claude AI로 생성해 Telegram으로 발송
실행: python -m english_learning.daily_vocab
GitHub Actions 스케줄러로 매일 자동 실행 가능
"""
import json
import os
import sys
from datetime import datetime, date
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv

load_dotenv()

PROFILE_PATH = Path(__file__).parent / "data" / "user_profile.json"
SENT_LOG_PATH = Path(__file__).parent / "data" / "sent_log.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

LEVEL_DESCRIPTIONS = {
    "A2": "초급 영어 학습자. 기초 단어와 일상 표현 위주로 선정해주세요.",
    "B1": "초중급 학습자. 일상 대화에 자주 쓰이는 단어와 숙어를 선정해주세요.",
    "B2": "중급 학습자. 비즈니스·뉴스에서 자주 접하는 단어와 관용표현을 선정해주세요.",
    "C1": "중상급 학습자. 고급 어휘, 뉘앙스가 있는 숙어, 격식체·비격식체 차이도 포함해주세요.",
    "C2": "고급 학습자. 문학·학술·뉴스에서 쓰이는 고급 어휘와 복잡한 관용표현을 선정해주세요.",
}


def load_profile() -> dict:
    if not PROFILE_PATH.exists():
        print("❌ 사용자 프로필이 없습니다. 먼저 수준 테스트를 실행하세요:")
        print("   python -m english_learning.level_assessment")
        sys.exit(1)
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return json.load(f)


def already_sent_today() -> bool:
    if not SENT_LOG_PATH.exists():
        return False
    with open(SENT_LOG_PATH, encoding="utf-8") as f:
        log = json.load(f)
    return log.get("last_sent_date") == str(date.today())


def save_sent_log(vocab_list: list[dict]) -> None:
    SENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log = {"last_sent_date": str(date.today()), "sent_vocab": vocab_list}
    with open(SENT_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def generate_vocab(level_code: str, count: int) -> list[dict]:
    """Claude API로 수준에 맞는 단어/숙어 목록 생성"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    level_desc = LEVEL_DESCRIPTIONS.get(level_code, LEVEL_DESCRIPTIONS["B1"])
    today_seed = str(date.today())  # 날짜별로 다른 단어 생성

    prompt = f"""오늘 날짜: {today_seed}
사용자 영어 수준: {level_code} — {level_desc}

위 수준에 맞는 영어 단어 또는 숙어 {count}개를 선정하고, 아래 JSON 형식으로만 답변하세요.
반드시 다양하게 (단어: 명사/동사/형용사/부사, 숙어: 비유적 표현/관용구) 섞어주세요.
오늘 날짜를 시드로 활용해 매일 다른 단어가 선정되도록 하세요.

JSON 형식 (배열):
[
  {{
    "type": "word",
    "english": "serendipity",
    "pronunciation": "/ˌserənˈdɪpɪti/",
    "korean": "우연한 행운, 뜻밖의 발견",
    "part_of_speech": "명사",
    "example_en": "It was pure serendipity that we met at the conference.",
    "example_ko": "우리가 그 컨퍼런스에서 만난 건 순전한 행운이었다.",
    "tip": "serendip(스리랑카 옛 이름) + ity → 동화 '세렌딥의 세 왕자'에서 유래"
  }},
  {{
    "type": "idiom",
    "english": "bite the bullet",
    "pronunciation": "",
    "korean": "이를 악물고 참다, 힘든 일을 받아들이다",
    "part_of_speech": "숙어",
    "example_en": "I hate going to the dentist, but I'll just have to bite the bullet.",
    "example_ko": "치과 가기 싫지만 그냥 참고 가야겠어.",
    "tip": "과거 수술 시 마취 없이 총알을 물어 통증을 참은 데서 유래"
  }}
]

JSON 배열만 출력하고, 다른 텍스트는 일절 포함하지 마세요."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # JSON 블록 마크다운이 있으면 제거
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)


def format_telegram_message(vocab_list: list[dict], profile: dict) -> str:
    today_str = datetime.now().strftime("%Y년 %m월 %d일")
    level_label = profile.get("level_label", "")

    lines = [
        f"📚 *오늘의 영어 학습* — {today_str}",
        f"📊 학습 수준: {level_label}",
        "",
    ]

    for i, item in enumerate(vocab_list, 1):
        pron = f" {item['pronunciation']}" if item.get("pronunciation") else ""
        lines.append(f"*{i}\\. {escape_md(item['english'])}*{escape_md(pron)}")
        lines.append(f"🏷 {escape_md(item['part_of_speech'])} \\| {escape_md(item['korean'])}")
        lines.append(f"💬 _{escape_md(item['example_en'])}_")
        lines.append(f"   → {escape_md(item['example_ko'])}")
        if item.get("tip"):
            lines.append(f"💡 {escape_md(item['tip'])}")
        lines.append("")

    lines.append("✏️ 오늘도 한 단어씩 차근차근\\! 🎯")
    return "\n".join(lines)


def escape_md(text: str) -> str:
    """Telegram MarkdownV2 특수문자 이스케이프"""
    special = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in str(text))


def send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않았습니다.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "MarkdownV2",
    }
    resp = requests.post(url, json=payload, timeout=30)
    if resp.ok:
        print("✅ 텔레그램 발송 성공!")
        return True
    else:
        print(f"❌ 텔레그램 발송 실패: {resp.status_code} {resp.text}")
        return False


def main(force: bool = False) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 영어 단어 발송 시작")

    if not force and already_sent_today():
        print("✅ 오늘은 이미 발송했습니다. (강제 실행: --force)")
        return

    profile = load_profile()
    level_code = profile["level_code"]
    count = profile["daily_vocab_count"]

    print(f"📊 수준: {profile['level_label']} | 오늘의 단어 수: {count}개")
    print("🤖 Claude로 단어 생성 중...")

    vocab_list = generate_vocab(level_code, count)
    print(f"✅ {len(vocab_list)}개 생성 완료")

    message = format_telegram_message(vocab_list, profile)

    # 콘솔 미리보기 (디버그용)
    print("\n── 발송 내용 미리보기 ─────────────────────")
    for item in vocab_list:
        print(f"  {item['english']} — {item['korean']}")
    print("──────────────────────────────────────────\n")

    ok = send_telegram(message)
    if ok:
        save_sent_log(vocab_list)


if __name__ == "__main__":
    force = "--force" in sys.argv
    main(force=force)
