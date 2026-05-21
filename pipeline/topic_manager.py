"""
Topic Manager for 어쩌다지식 YouTube Pipeline.

Manages topic queue, selection, and lifecycle tracking.
Topics are stored in data/topic_queue.json.
"""

from __future__ import annotations

import json
import logging
import random
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

TOPIC_QUEUE_FILE = Path("data/topic_queue.json")

CATEGORY_WEIGHTS = {
    "psychology": 35,
    "life": 40,
    "tech": 25,
}


@dataclass
class Topic:
    id: str
    title_idea: str
    category: str  # "psychology" | "life" | "tech"
    keywords: list[str]
    hook: str = ""
    used: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    used_at: Optional[str] = None
    priority: int = 100

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Topic":
        return cls(
            id=data["id"],
            title_idea=data["title_idea"],
            category=data["category"],
            keywords=data.get("keywords", []),
            hook=data.get("hook", ""),
            used=data.get("used", False),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            used_at=data.get("used_at"),
            priority=data.get("priority", 100),
        )


class TopicManager:
    """Manages the topic queue for the YouTube channel pipeline."""

    def __init__(self, queue_file: Path = TOPIC_QUEUE_FILE):
        self.queue_file = Path(queue_file)
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = {}
        self._topics: list[Topic] = []
        self.load_queue()

    def load_queue(self) -> None:
        """Load topic queue from JSON file."""
        if not self.queue_file.exists():
            logger.warning(f"Topic queue file not found: {self.queue_file}. Starting empty.")
            self._data = {"last_updated": datetime.now(timezone.utc).isoformat(), "topics": []}
            self._topics = []
            return

        try:
            with open(self.queue_file, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            self._topics = [Topic.from_dict(t) for t in self._data.get("topics", [])]
            logger.info(f"Loaded {len(self._topics)} topics from queue ({self._unused_count()} unused)")
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error(f"Failed to parse topic queue: {exc}")
            raise

    def _save_queue(self) -> None:
        """Persist topic queue to JSON file."""
        self._data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._data["topics"] = [t.to_dict() for t in self._topics]
        with open(self.queue_file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        logger.debug(f"Topic queue saved to {self.queue_file}")

    def _unused_count(self) -> int:
        return sum(1 for t in self._topics if not t.used)

    def get_next_topic(
        self, category: Optional[str] = None, topic_id: Optional[str] = None
    ) -> Optional[Topic]:
        """
        Get the next topic to use.

        Args:
            category: Force a specific category (psychology/life/tech).
            topic_id: Force a specific topic by ID.

        Returns:
            Topic to produce next, or None if queue is exhausted.
        """
        # Force specific topic
        if topic_id:
            for topic in self._topics:
                if topic.id == topic_id and not topic.used:
                    logger.info(f"Forced topic selected: {topic.id} — {topic.title_idea}")
                    return topic
            logger.error(f"Topic ID {topic_id} not found or already used.")
            return None

        unused = [t for t in self._topics if not t.used]
        if not unused:
            logger.warning("All topics have been used! Add more topics to the queue.")
            return None

        # Filter by category if specified
        if category:
            pool = [t for t in unused if t.category == category]
            if not pool:
                logger.warning(f"No unused topics in category '{category}'. Falling back to any category.")
                pool = unused
        else:
            # Weighted random category selection
            category = self._weighted_category_pick(unused)
            pool = [t for t in unused if t.category == category]
            if not pool:
                pool = unused

        # Pick by priority (lower number = higher priority), with small randomness among top-3
        pool.sort(key=lambda t: t.priority)
        top_n = pool[:3]
        selected = random.choice(top_n)

        logger.info(
            f"Selected topic: [{selected.category}] {selected.id} — {selected.title_idea}"
        )
        return selected

    def _weighted_category_pick(self, available: list[Topic]) -> str:
        """Pick a category using weights, restricted to categories with available topics."""
        available_cats = {t.category for t in available}
        weights = {k: v for k, v in CATEGORY_WEIGHTS.items() if k in available_cats}
        if not weights:
            return random.choice(list(available_cats))

        cats = list(weights.keys())
        w = [weights[c] for c in cats]
        return random.choices(cats, weights=w, k=1)[0]

    def mark_used(self, topic_id: str) -> None:
        """Mark a topic as used so it won't be selected again."""
        for topic in self._topics:
            if topic.id == topic_id:
                topic.used = True
                topic.used_at = datetime.now(timezone.utc).isoformat()
                self._save_queue()
                logger.info(f"Marked topic {topic_id} as used.")
                return
        logger.warning(f"Topic {topic_id} not found when trying to mark used.")

    def add_topic(
        self,
        title_idea: str,
        category: str,
        keywords: list[str],
        hook: str = "",
        priority: int = 100,
    ) -> Topic:
        """Add a new topic to the queue."""
        if category not in CATEGORY_WEIGHTS:
            raise ValueError(f"Invalid category '{category}'. Must be one of: {list(CATEGORY_WEIGHTS)}")

        new_topic = Topic(
            id=f"topic_{uuid.uuid4().hex[:8]}",
            title_idea=title_idea,
            category=category,
            keywords=keywords,
            hook=hook,
            priority=priority,
        )
        self._topics.append(new_topic)
        self._save_queue()
        logger.info(f"Added new topic: {new_topic.id} — {title_idea}")
        return new_topic

    def get_topic_by_id(self, topic_id: str) -> Optional[Topic]:
        """Retrieve a topic by its ID."""
        for topic in self._topics:
            if topic.id == topic_id:
                return topic
        return None

    def list_unused(self, category: Optional[str] = None) -> list[Topic]:
        """Return all unused topics, optionally filtered by category."""
        unused = [t for t in self._topics if not t.used]
        if category:
            unused = [t for t in unused if t.category == category]
        return sorted(unused, key=lambda t: t.priority)

    def queue_stats(self) -> dict:
        """Return summary statistics about the topic queue."""
        total = len(self._topics)
        used = sum(1 for t in self._topics if t.used)
        by_cat: dict[str, dict] = {}
        for cat in CATEGORY_WEIGHTS:
            cat_topics = [t for t in self._topics if t.category == cat]
            by_cat[cat] = {
                "total": len(cat_topics),
                "used": sum(1 for t in cat_topics if t.used),
                "available": sum(1 for t in cat_topics if not t.used),
            }
        return {
            "total": total,
            "used": used,
            "available": total - used,
            "by_category": by_cat,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tm = TopicManager()
    stats = tm.queue_stats()
    print(f"\n📊 Topic Queue Stats:")
    print(f"  Total: {stats['total']} | Used: {stats['used']} | Available: {stats['available']}")
    for cat, s in stats["by_category"].items():
        print(f"  [{cat}] available: {s['available']}/{s['total']}")

    next_topic = tm.get_next_topic()
    if next_topic:
        print(f"\n▶ Next topic: {next_topic.title_idea}")
        print(f"  Category: {next_topic.category}")
        print(f"  Keywords: {', '.join(next_topic.keywords)}")
