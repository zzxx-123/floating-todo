"""Data model for cards and their tasks."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .constants import (
    ACCENT_BY_KEY,
    APPEARANCES,
    DEFAULT_ACCENT,
    DEFAULT_APPEARANCE,
    MAX_CARDS,
    MAX_TASK_LEN,
    MAX_TASKS_PER_CARD,
    MAX_TITLE_LEN,
)

SCHEMA_VERSION = 2


class StateFormatError(ValueError):
    """Raised when a state document cannot be interpreted safely."""


def new_id() -> str:
    return uuid.uuid4().hex


def clean_title(value: Any, fallback: str = "未命名清单") -> str:
    if not isinstance(value, str):
        return fallback
    value = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    if not value:
        return fallback
    return value[:MAX_TITLE_LEN]


def clean_task_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    if not value:
        return None
    return value[:MAX_TASK_LEN]


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    return default


def _as_position(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        number = int(value)
        if -200_000 <= number <= 200_000:
            return number
    return default


@dataclass
class Task:
    id: str = field(default_factory=new_id)
    text: str = ""
    done: bool = False
    created_at: float = field(default_factory=time.time)

    @classmethod
    def create(cls, text: str) -> "Task":
        cleaned = clean_task_text(text)
        if cleaned is None:
            raise ValueError("任务内容不能为空")
        return cls(id=new_id(), text=cleaned, done=False, created_at=time.time())

    @classmethod
    def from_dict(cls, raw: Any) -> "Task | None":
        if not isinstance(raw, dict):
            return None
        text = clean_task_text(raw.get("text"))
        if text is None:
            return None
        task_id = raw.get("id")
        if not isinstance(task_id, str) or not task_id.strip():
            task_id = new_id()
        created_at = raw.get("created_at", time.time())
        if not isinstance(created_at, (int, float)) or isinstance(created_at, bool):
            created_at = time.time()
        return cls(
            id=task_id.strip()[:80],
            text=text,
            done=_as_bool(raw.get("done")),
            created_at=float(created_at),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "done": self.done,
            "created_at": self.created_at,
        }


@dataclass
class Card:
    id: str = field(default_factory=new_id)
    title: str = "今天"
    accent: str = DEFAULT_ACCENT
    x: int = 0
    y: int = 0
    collapsed: bool = False
    pinned: bool = True
    tasks: list[Task] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.title = clean_title(self.title)
        if self.accent not in ACCENT_BY_KEY:
            self.accent = DEFAULT_ACCENT
        self.x = _as_position(self.x)
        self.y = _as_position(self.y)
        self.tasks = self.tasks[:MAX_TASKS_PER_CARD]

    @property
    def completed_count(self) -> int:
        return sum(1 for task in self.tasks if task.done)

    @property
    def total_count(self) -> int:
        return len(self.tasks)

    @property
    def remaining_count(self) -> int:
        return self.total_count - self.completed_count

    @property
    def progress(self) -> float:
        if not self.tasks:
            return 0.0
        return self.completed_count / len(self.tasks)

    def add_task(self, text: str) -> Task | None:
        if len(self.tasks) >= MAX_TASKS_PER_CARD:
            return None
        task = Task.create(text)
        self.tasks.append(task)
        return task

    def find_task(self, task_id: str) -> Task | None:
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def remove_task(self, task_id: str) -> bool:
        for index, task in enumerate(self.tasks):
            if task.id == task_id:
                del self.tasks[index]
                return True
        return False

    def clear_completed(self) -> int:
        before = len(self.tasks)
        self.tasks = [task for task in self.tasks if not task.done]
        return before - len(self.tasks)

    def reorder_task(self, task_id: str, offset: int) -> bool:
        for index, task in enumerate(self.tasks):
            if task.id == task_id:
                target = max(0, min(len(self.tasks) - 1, index + offset))
                if target == index:
                    return False
                self.tasks.insert(target, self.tasks.pop(index))
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "accent": self.accent,
            "x": self.x,
            "y": self.y,
            "collapsed": self.collapsed,
            "pinned": self.pinned,
            "tasks": [task.to_dict() for task in self.tasks],
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "Card | None":
        if not isinstance(raw, dict):
            return None
        card_id = raw.get("id")
        if not isinstance(card_id, str) or not card_id.strip():
            card_id = new_id()
        tasks: list[Task] = []
        raw_tasks = raw.get("tasks")
        if isinstance(raw_tasks, list):
            seen_task_ids: set[str] = set()
            for item in raw_tasks:
                task = Task.from_dict(item)
                if task is None:
                    continue
                if task.id in seen_task_ids:
                    task.id = new_id()
                seen_task_ids.add(task.id)
                tasks.append(task)
                if len(tasks) >= MAX_TASKS_PER_CARD:
                    break
        return cls(
            id=card_id.strip()[:80],
            title=clean_title(raw.get("title"), "清单"),
            accent=raw.get("accent") if isinstance(raw.get("accent"), str) else DEFAULT_ACCENT,
            x=_as_position(raw.get("x")),
            y=_as_position(raw.get("y")),
            collapsed=_as_bool(raw.get("collapsed")),
            pinned=_as_bool(raw.get("pinned"), default=True),
            tasks=tasks,
        )


@dataclass
class AppState:
    version: int = SCHEMA_VERSION
    onboarding_dismissed: bool = False
    appearance: str = DEFAULT_APPEARANCE
    cards: list[Card] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.appearance not in APPEARANCES:
            self.appearance = DEFAULT_APPEARANCE

    @property
    def card_count(self) -> int:
        return len(self.cards)

    def find_card(self, card_id: str) -> Card | None:
        for card in self.cards:
            if card.id == card_id:
                return card
        return None

    def add_card(self, title: str = "新清单", accent: str = DEFAULT_ACCENT) -> Card | None:
        if len(self.cards) >= MAX_CARDS:
            return None
        card = Card(title=clean_title(title, "新清单"), accent=accent)
        self.cards.append(card)
        return card

    def remove_card(self, card_id: str) -> bool:
        for index, card in enumerate(self.cards):
            if card.id == card_id:
                del self.cards[index]
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": SCHEMA_VERSION,
            "onboarding_dismissed": self.onboarding_dismissed,
            "appearance": self.appearance,
            "cards": [card.to_dict() for card in self.cards],
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "AppState":
        if not isinstance(raw, dict):
            raise StateFormatError("数据文件不是对象")
        version = raw.get("version", SCHEMA_VERSION)
        if not isinstance(version, int) or isinstance(version, bool):
            raise StateFormatError("数据版本无效")
        if version > SCHEMA_VERSION:
            raise StateFormatError(f"数据版本 {version} 高于当前支持的版本")
        appearance = raw.get("appearance", DEFAULT_APPEARANCE)
        if appearance not in APPEARANCES:
            appearance = DEFAULT_APPEARANCE
        raw_cards = raw.get("cards", [])
        if not isinstance(raw_cards, list):
            raise StateFormatError("卡片列表无效")
        cards: list[Card] = []
        seen_ids: set[str] = set()
        for item in raw_cards:
            card = Card.from_dict(item)
            if card is None:
                continue
            if card.id in seen_ids:
                card.id = new_id()
            seen_ids.add(card.id)
            cards.append(card)
            if len(cards) >= MAX_CARDS:
                break
        return cls(
            version=SCHEMA_VERSION,
            onboarding_dismissed=_as_bool(raw.get("onboarding_dismissed")),
            appearance=appearance,
            cards=cards,
        )

    def ensure_card(self) -> Card:
        if not self.cards:
            self.cards.append(Card(title="今天"))
        return self.cards[0]
