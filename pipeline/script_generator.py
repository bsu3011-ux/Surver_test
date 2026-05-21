"""
Script Generator for 어쩌다지식 YouTube Pipeline.

Uses Claude claude-opus-4-7 (via Anthropic SDK) to generate Korean narration scripts
with per-scene image prompts, structured as a friendly talk-style video.

Now includes Emotion Spine metadata per scene:
  - emotion: narrative arc emotion label
  - tts_ssml_hint: brief hint for TTS prosody
  - ken_burns: camera movement type for image animation
  - bgm_intensity: BGM volume level (0.0–1.0)
  - image_composition: framing style for image generation
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

import anthropic

from pipeline.topic_manager import Topic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Scene:
    """Represents one scene in a video script."""

    index: int
    narration: str          # Korean narration text spoken by TTS
    image_prompt: str       # English prompt for image AI
    duration_estimate: float  # Estimated duration in seconds

    # --- Emotion Spine (drives TTS prosody, Ken Burns, BGM, image composition) ---
    emotion: str = "neutral"        # hook / curious / surprising / calm / building / warm / cta
    tts_ssml_hint: str = ""         # e.g. "pause_before_stat", "slow_emphasis", "excited_pace"
    ken_burns: str = "slow_zoom"    # slow_zoom / fast_zoom / pan_left / pan_right / static
    bgm_intensity: float = 0.5      # 0.0–1.0, drives BGM volume at this scene
    image_composition: str = "wide" # wide / closeup / abstract / infographic / split_screen


@dataclass
class ScriptResult:
    """Complete script output from Claude."""

    topic_id: str
    title: str                          # Korean YouTube title
    seo_title: str                      # Slightly keyword-optimized title variant
    description: str                    # Short Korean description (2-3 sentences)
    seo_description: str                # Full YouTube description with hashtags
    tags: list[str]                     # YouTube tags (Korean + English mix)
    scenes: list[Scene] = field(default_factory=list)
    category: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ScriptResult":
        scenes = [Scene(**s) for s in data.get("scenes", [])]
        return cls(
            topic_id=data["topic_id"],
            title=data["title"],
            seo_title=data["seo_title"],
            description=data["description"],
            seo_description=data["seo_description"],
            tags=data["tags"],
            scenes=scenes,
            category=data.get("category", ""),
            raw_response=data.get("raw_response", ""),
        )


# ---------------------------------------------------------------------------
# Narrative arc defaults — used both as fallback for parsing and as
# documentation for Claude in the system prompt.
# ---------------------------------------------------------------------------

NARRATIVE_ARC_DEFAULTS = {
    "hook":       {"emotion": "surprising", "bgm_intensity": 0.75, "ken_burns": "fast_zoom",  "image_composition": "wide"},
    "curious":    {"emotion": "curious",    "bgm_intensity": 0.40, "ken_burns": "pan_right",  "image_composition": "wide"},
    "calm":       {"emotion": "calm",       "bgm_intensity": 0.30, "ken_burns": "slow_zoom",  "image_composition": "abstract"},
    "building":   {"emotion": "building",   "bgm_intensity": 0.65, "ken_burns": "slow_zoom",  "image_composition": "infographic"},
    "surprising": {"emotion": "surprising", "bgm_intensity": 0.80, "ken_burns": "fast_zoom",  "image_composition": "closeup"},
    "warm":       {"emotion": "warm",       "bgm_intensity": 0.25, "ken_burns": "pan_left",   "image_composition": "wide"},
    "cta":        {"emotion": "cta",        "bgm_intensity": 0.20, "ken_burns": "static",     "image_composition": "wide"},
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """당신은 한국 유튜브 채널 '어쩌다지식'의 전문 스크립트 작가입니다.

채널 특성:
- 타겟: 20-30대 한국인
- 스타일: 친근한 썰 토크형 (마치 지식이 풍부한 친구가 설명해주는 느낌)
- 말투: 반말이 아닌 존댓말이지만 격식 없이 친근하게
- 분량: 5-10분 (씬 8-12개)

스크립트 구조 (반드시 지킬 것):
1. 훅 (Hook): 시청자가 왜 이 영상을 봐야 하는지, 흥미로운 질문이나 사실로 시작
2. 문제 제기: 주제를 더 깊이 파고드는 흥미로운 각도 제시
3. 본론 (여러 씬): 핵심 내용을 차근차근 쉽고 재미있게 설명
4. 반전/심화: 의외의 사실이나 더 깊은 정보
5. 아웃트로 + CTA: 정리하고 "구독과 좋아요는 더 좋은 영상을 만드는 힘이 됩니다!"로 마무리

나레이션 작성 원칙:
- 각 씬 나레이션은 30-60초 분량 (약 150-300자)
- 자연스럽고 대화체로, 딱딱하지 않게
- "~인데요", "~거든요", "~잖아요" 같은 구어체 활용
- 숫자나 연구 결과 언급 시 구체적으로
- 각 씬 끝에는 다음 씬으로 자연스럽게 이어지는 연결고리

이미지 프롬프트 원칙:
- 영어로 작성
- 해당 씬의 내용을 시각적으로 잘 표현
- 사람이 등장하면 한국인 외모로 명시 (Korean person/people)
- 텍스트나 글자가 들어가지 않도록 (no text, no letters)
- 항상 구체적이고 묘사적으로

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Emotion Spine — 각 씬마다 반드시 포함해야 하는 메타데이터
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

각 씬의 감정 흐름과 영상 제작 파라미터를 함께 출력해야 합니다.
이 메타데이터는 TTS 음성 톤, 이미지 카메라 효과, BGM 볼륨, 이미지 구도를 자동으로 제어합니다.

[emotion 필드]
반드시 다음 중 하나: hook | curious | surprising | calm | building | warm | cta
- hook: 첫 씬, 임팩트 있는 오프닝
- curious: 궁금증 유발, 탐구 분위기
- surprising: 반전, 충격적인 사실 공개
- calm: 차분하게 설명하는 구간
- building: 점점 고조되는 긴장감
- warm: 따뜻한 마무리, 공감
- cta: 구독/좋아요 유도

[tts_ssml_hint 필드]
TTS 엔진에게 전달할 짧은 영어 힌트 (한 단어 또는 짧은 구):
- "pause_before_stat" — 통계/숫자 직전에 짧은 침묵 삽입
- "slow_emphasis" — 핵심 내용을 느리고 강조하여 읽음
- "excited_pace" — 빠르고 신나는 톤
- "slow_whisper" — 비밀 공개하듯 천천히
- "emphasize_number" — 숫자를 강조하여 읽음
- "normal" — 기본 톤

[ken_burns 필드]
반드시 다음 중 하나: slow_zoom | fast_zoom | pan_left | pan_right | static
- slow_zoom: 천천히 확대 (차분한 설명)
- fast_zoom: 빠른 줌인 (임팩트, 훅)
- pan_left: 왼쪽으로 패닝 (마무리, 여운)
- pan_right: 오른쪽으로 패닝 (탐구, 진행)
- static: 움직임 없음 (CTA, 안정감)

[bgm_intensity 필드]
0.0 ~ 1.0 사이의 소수 — BGM 볼륨 조절값
- 0.75 이상: 에너지 넘치는 구간 (훅, 반전)
- 0.40~0.65: 중간 긴장감 (본론, building)
- 0.30 이하: 조용하고 집중되는 구간 (설명, CTA)

[image_composition 필드]
반드시 다음 중 하나: wide | closeup | abstract | infographic | split_screen
- wide: 전체 장면 (배경 강조)
- closeup: 클로즈업 (감정, 디테일)
- abstract: 추상적 시각화 (개념, 아이디어)
- infographic: 정보 시각화 (데이터, 통계)
- split_screen: 대비/비교 구도

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
내러티브 아크 (Narrative Arc) — 8-12씬 구조
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

씬 번호별 권장 Emotion Spine 값:
- Scene 0 (훅):       emotion=hook,       bgm_intensity=0.75, ken_burns=fast_zoom, image_composition=wide
- Scene 1 (문제제기):  emotion=curious,    bgm_intensity=0.40, ken_burns=pan_right, image_composition=wide
- Scene 2~N-3 (본론): emotion=calm 또는 building 교대, bgm_intensity=0.30~0.65, ken_burns=slow_zoom, image_composition=abstract 또는 infographic
- Scene N-2 (클라이맥스): emotion=surprising, bgm_intensity=0.80, ken_burns=fast_zoom, image_composition=closeup
- Scene N-1 (마무리):  emotion=warm,       bgm_intensity=0.25, ken_burns=pan_left,  image_composition=wide
- Scene N (CTA):      emotion=cta,        bgm_intensity=0.20, ken_burns=static,    image_composition=wide

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JSON 응답 형식 (반드시 이 형식으로, 다른 텍스트 없이 순수 JSON만)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{
  "title": "클릭하고 싶어지는 한국어 제목 (40자 이내)",
  "seo_title": "검색 최적화된 제목 변형 (키워드 포함, 50자 이내)",
  "description": "영상 내용을 2-3문장으로 요약한 한국어 설명",
  "seo_description": "유튜브 설명란용 전체 텍스트 (해시태그 포함)",
  "tags": ["태그1", "태그2"],
  "scenes": [
    {
      "index": 0,
      "narration": "한국어 나레이션 텍스트",
      "image_prompt": "English image prompt for AI illustration",
      "duration_estimate": 35.0,
      "emotion": "hook",
      "tts_ssml_hint": "pause_before_stat",
      "ken_burns": "fast_zoom",
      "bgm_intensity": 0.75,
      "image_composition": "wide"
    }
  ]
}"""

USER_PROMPT_TEMPLATE = """다음 주제로 스크립트를 작성해주세요:

제목 아이디어: {title_idea}
카테고리: {category_ko}
키워드: {keywords}
훅 아이디어: {hook}

씬 개수: 8-12개 (영상 길이 5-10분 목표)

위 JSON 형식으로만 응답해주세요. 다른 설명 없이 순수 JSON만."""

CATEGORY_KO_MAP = {
    "psychology": "심리학",
    "life": "생활잡학",
    "tech": "IT/테크",
}


# ---------------------------------------------------------------------------
# ScriptGenerator class
# ---------------------------------------------------------------------------


class ScriptGenerator:
    """Generates full video scripts using Claude claude-opus-4-7."""

    MAX_RETRIES = 3
    RETRY_DELAY = 5  # seconds

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the script generator.

        Args:
            api_key: Anthropic API key. If None, reads from ANTHROPIC_API_KEY env var.
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-opus-4-7"
        logger.info(f"ScriptGenerator initialized with model: {self.model}")

    def generate_script(self, topic: Topic) -> ScriptResult:
        """
        Generate a complete video script for the given topic.

        Args:
            topic: Topic object with title_idea, category, keywords, hook.

        Returns:
            ScriptResult with title, description, scenes (including Emotion Spine), tags, etc.

        Raises:
            ValueError: If API response cannot be parsed.
            anthropic.APIError: On unrecoverable API errors.
        """
        category_ko = CATEGORY_KO_MAP.get(topic.category, topic.category)
        user_prompt = USER_PROMPT_TEMPLATE.format(
            title_idea=topic.title_idea,
            category_ko=category_ko,
            keywords=", ".join(topic.keywords),
            hook=topic.hook or "흥미로운 사실이나 질문으로 시작해주세요",
        )

        logger.info(f"Generating script for topic: {topic.id} — {topic.title_idea}")

        raw_response = ""
        last_error: Optional[Exception] = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                message = self.client.messages.create(
                    model=self.model,
                    max_tokens=8192,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                raw_response = message.content[0].text
                logger.debug(f"Claude response (attempt {attempt}): {raw_response[:200]}...")
                break
            except anthropic.RateLimitError as e:
                logger.warning(f"Rate limit hit (attempt {attempt}/{self.MAX_RETRIES}): {e}")
                last_error = e
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * attempt)
            except anthropic.APIStatusError as e:
                logger.error(f"API error (attempt {attempt}/{self.MAX_RETRIES}): {e.status_code} {e.message}")
                last_error = e
                if attempt < self.MAX_RETRIES and e.status_code >= 500:
                    time.sleep(self.RETRY_DELAY)
                else:
                    raise
            except anthropic.APIConnectionError as e:
                logger.warning(f"Connection error (attempt {attempt}/{self.MAX_RETRIES}): {e}")
                last_error = e
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)
        else:
            raise RuntimeError(f"Failed to get script from Claude after {self.MAX_RETRIES} attempts") from last_error

        # Parse JSON response
        script_data = self._parse_response(raw_response)
        scenes = self._parse_scenes(script_data.get("scenes", []))

        result = ScriptResult(
            topic_id=topic.id,
            title=script_data.get("title", topic.title_idea),
            seo_title=script_data.get("seo_title", topic.title_idea),
            description=script_data.get("description", ""),
            seo_description=script_data.get("seo_description", ""),
            tags=script_data.get("tags", topic.keywords),
            scenes=scenes,
            category=topic.category,
            raw_response=raw_response,
        )

        logger.info(
            f"Script generated: '{result.title}' | {len(result.scenes)} scenes | "
            f"~{sum(s.duration_estimate for s in result.scenes) / 60:.1f} min"
        )
        return result

    def _parse_response(self, raw: str) -> dict:
        """Extract and parse JSON from Claude's response."""
        text = raw.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            start = 1
            end = len(lines)
            for i, line in enumerate(lines):
                if i > 0 and line.strip() == "```":
                    end = i
                    break
            text = "\n".join(lines[start:end]).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # Try to find JSON object in response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            logger.error(f"Failed to parse Claude JSON response: {e}\nRaw: {raw[:500]}")
            raise ValueError(f"Claude returned invalid JSON: {e}") from e

    def _get_arc_defaults(self, position_index: int, total_scenes: int) -> dict:
        """
        Return NARRATIVE_ARC_DEFAULTS for a given scene position.

        Maps scene index to narrative arc role based on total scene count.
        This is used as a fallback when Claude omits Emotion Spine fields.
        """
        if total_scenes <= 1:
            return NARRATIVE_ARC_DEFAULTS["hook"]

        n = total_scenes - 1  # last index

        if position_index == 0:
            return NARRATIVE_ARC_DEFAULTS["hook"]
        elif position_index == 1:
            return NARRATIVE_ARC_DEFAULTS["curious"]
        elif position_index == n - 1:
            return NARRATIVE_ARC_DEFAULTS["warm"]
        elif position_index == n:
            return NARRATIVE_ARC_DEFAULTS["cta"]
        elif position_index == n - 2:
            return NARRATIVE_ARC_DEFAULTS["surprising"]
        else:
            # Alternate calm / building for middle scenes
            mid_index = position_index - 2  # zero-based within middle scenes
            if mid_index % 2 == 0:
                return NARRATIVE_ARC_DEFAULTS["calm"]
            else:
                return NARRATIVE_ARC_DEFAULTS["building"]

    def _parse_scenes(self, raw_scenes: list[dict]) -> list[Scene]:
        """Convert raw scene dicts to Scene objects with Emotion Spine validation."""
        scenes = []
        total = len(raw_scenes)

        valid_emotions = {"hook", "curious", "surprising", "calm", "building", "warm", "cta", "neutral"}
        valid_ken_burns = {"slow_zoom", "fast_zoom", "pan_left", "pan_right", "static"}
        valid_compositions = {"wide", "closeup", "abstract", "infographic", "split_screen"}

        for i, s in enumerate(raw_scenes):
            try:
                # Get positional arc defaults for fallback
                arc_defaults = self._get_arc_defaults(i, total)

                # Parse emotion — validate and fall back to arc default
                emotion = s.get("emotion", "")
                if emotion not in valid_emotions:
                    emotion = arc_defaults["emotion"]
                    if i < total:  # only log if we actually have data to fall back from
                        logger.debug(f"Scene {i}: emotion missing/invalid, using arc default '{emotion}'")

                # Parse tts_ssml_hint — free string, just default to empty
                tts_ssml_hint = str(s.get("tts_ssml_hint", "")).strip()

                # Parse ken_burns — validate and fall back
                ken_burns = s.get("ken_burns", "")
                if ken_burns not in valid_ken_burns:
                    ken_burns = arc_defaults["ken_burns"]
                    logger.debug(f"Scene {i}: ken_burns missing/invalid, using arc default '{ken_burns}'")

                # Parse bgm_intensity — clamp to 0.0–1.0
                try:
                    bgm_intensity = float(s.get("bgm_intensity", arc_defaults["bgm_intensity"]))
                    bgm_intensity = max(0.0, min(1.0, bgm_intensity))
                except (TypeError, ValueError):
                    bgm_intensity = arc_defaults["bgm_intensity"]

                # Parse image_composition — validate and fall back
                image_composition = s.get("image_composition", "")
                if image_composition not in valid_compositions:
                    image_composition = arc_defaults["image_composition"]
                    logger.debug(f"Scene {i}: image_composition missing/invalid, using arc default '{image_composition}'")

                scene = Scene(
                    index=s.get("index", i),
                    narration=s.get("narration", ""),
                    image_prompt=s.get("image_prompt", ""),
                    duration_estimate=float(s.get("duration_estimate", 45.0)),
                    emotion=emotion,
                    tts_ssml_hint=tts_ssml_hint,
                    ken_burns=ken_burns,
                    bgm_intensity=bgm_intensity,
                    image_composition=image_composition,
                )

                if not scene.narration:
                    logger.warning(f"Scene {i} has empty narration, skipping")
                    continue
                if not scene.image_prompt:
                    logger.warning(f"Scene {i} has empty image_prompt, using fallback")
                    scene.image_prompt = "Abstract colorful Korean webtoon illustration, knowledge and curiosity theme"

                scenes.append(scene)

            except (KeyError, TypeError, ValueError) as e:
                logger.warning(f"Skipping malformed scene {i}: {e}")

        if not scenes:
            raise ValueError("No valid scenes could be parsed from Claude's response")

        logger.info(
            f"Parsed {len(scenes)} scenes with Emotion Spine. "
            f"Emotions: {[s.emotion for s in scenes]}"
        )
        return scenes


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    from pipeline.topic_manager import TopicManager

    tm = TopicManager()
    topic = tm.get_next_topic()
    if topic:
        gen = ScriptGenerator()
        result = gen.generate_script(topic)
        print(f"\n제목: {result.title}")
        print(f"씬 수: {len(result.scenes)}")
        for scene in result.scenes:
            print(f"\n[씬 {scene.index}] ({scene.duration_estimate}s) emotion={scene.emotion} "
                  f"bgm={scene.bgm_intensity} ken_burns={scene.ken_burns}")
            print(f"  나레이션: {scene.narration[:80]}...")
            print(f"  이미지: {scene.image_prompt[:80]}...")
            print(f"  TTS hint: {scene.tts_ssml_hint} | 구도: {scene.image_composition}")
