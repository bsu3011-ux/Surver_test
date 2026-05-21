"""
Script Generator for 어쩌다지식 YouTube Pipeline.

Uses Claude claude-opus-4-7 (via Anthropic SDK) to generate Korean narration scripts
with per-scene image prompts, structured as a friendly talk-style video.
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
    image_prompt: str       # English prompt for Imagen
    duration_estimate: float  # Estimated duration in seconds


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

JSON 응답 형식 (반드시 이 형식으로):
{
  "title": "클릭하고 싶어지는 한국어 제목 (40자 이내)",
  "seo_title": "검색 최적화된 제목 변형 (키워드 포함, 50자 이내)",
  "description": "영상 내용을 2-3문장으로 요약한 한국어 설명",
  "seo_description": "유튜브 설명란용 전체 텍스트 (해시태그 포함)",
  "tags": ["태그1", "태그2", ...],
  "scenes": [
    {
      "index": 0,
      "narration": "한국어 나레이션 텍스트",
      "image_prompt": "English image prompt for AI illustration",
      "duration_estimate": 45.0
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
            ScriptResult with title, description, scenes, tags, etc.

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

    def _parse_scenes(self, raw_scenes: list[dict]) -> list[Scene]:
        """Convert raw scene dicts to Scene objects with validation."""
        scenes = []
        for i, s in enumerate(raw_scenes):
            try:
                scene = Scene(
                    index=s.get("index", i),
                    narration=s.get("narration", ""),
                    image_prompt=s.get("image_prompt", ""),
                    duration_estimate=float(s.get("duration_estimate", 45.0)),
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
            print(f"\n[씬 {scene.index}] ({scene.duration_estimate}s)")
            print(f"  나레이션: {scene.narration[:80]}...")
            print(f"  이미지: {scene.image_prompt[:80]}...")
