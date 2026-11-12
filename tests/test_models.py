from __future__ import annotations

import unittest

from floating_todo.constants import MAX_TASK_LEN, MAX_TASKS_PER_CARD, MAX_TITLE_LEN
from floating_todo.models import AppState, Card, StateFormatError, Task


class TaskModelTests(unittest.TestCase):
    def test_create_trims_and_flattens_whitespace(self) -> None:
        task = Task.create("  写周报\n 明天前  ")
        self.assertEqual(task.text, "写周报 明天前")
        self.assertFalse(task.done)

    def test_create_rejects_blank(self) -> None:
        with self.assertRaises(ValueError):
            Task.create(" \n\t ")

    def test_long_task_is_clamped(self) -> None:
        task = Task.create("x" * (MAX_TASK_LEN + 50))
        self.assertEqual(len(task.text), MAX_TASK_LEN)

    def test_round_trip(self) -> None:
        task = Task.create("买牛奶")
        task.done = True
        restored = Task.from_dict(task.to_dict())
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.id, task.id)
        self.assertEqual(restored.text, "买牛奶")
        self.assertTrue(restored.done)

    def test_invalid_task_skipped(self) -> None:
        self.assertIsNone(Task.from_dict(None))
        self.assertIsNone(Task.from_dict({}))
        self.assertIsNone(Task.from_dict({"text": "   "}))


class CardModelTests(unittest.TestCase):
    def test_progress(self) -> None:
        card = Card()
        card.add_task("a")
        card.add_task("b")
        card.tasks[0].done = True
        self.assertEqual(card.completed_count, 1)
        self.assertEqual(card.remaining_count, 1)
        self.assertAlmostEqual(card.progress, 0.5)
        self.assertEqual(card.clear_completed(), 1)
        self.assertEqual(card.total_count, 1)

    def test_task_limit(self) -> None:
        card = Card()
        for index in range(MAX_TASKS_PER_CARD):
            self.assertIsNotNone(card.add_task(f"task {index}"))
        self.assertIsNone(card.add_task("one too many"))
        self.assertEqual(len(card.tasks), MAX_TASKS_PER_CARD)

    def test_title_is_clamped(self) -> None:
        card = Card(title="长" * (MAX_TITLE_LEN + 20))
        self.assertEqual(len(card.title), MAX_TITLE_LEN)

    def test_unknown_accent_falls_back(self) -> None:
        card = Card(accent="not-a-color")
        self.assertEqual(card.accent, "coral")

    def test_round_trip(self) -> None:
        card = Card(title="工作", accent="mint", x=100, y=200, collapsed=True, pinned=False)
        card.add_task("完成报告")
        restored = Card.from_dict(card.to_dict())
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.title, "工作")
        self.assertEqual(restored.accent, "mint")
        self.assertEqual((restored.x, restored.y), (100, 200))
        self.assertTrue(restored.collapsed)
        self.assertFalse(restored.pinned)
        self.assertEqual(len(restored.tasks), 1)

    def test_duplicate_task_ids_are_made_unique(self) -> None:
        raw = {
            "id": "card",
            "title": "x",
            "tasks": [
                {"id": "same", "text": "one", "done": False},
                {"id": "same", "text": "two", "done": True},
            ],
        }
        card = Card.from_dict(raw)
        assert card is not None
        self.assertEqual(len(card.tasks), 2)
        self.assertNotEqual(card.tasks[0].id, card.tasks[1].id)


class AppStateTests(unittest.TestCase):
    def test_empty_state_has_no_cards(self) -> None:
        state = AppState.from_dict({"version": 1, "cards": []})
        self.assertEqual(state.cards, [])

    def test_ensure_card(self) -> None:
        state = AppState()
        card = state.ensure_card()
        self.assertEqual(card.title, "今天")
        self.assertIs(state.cards[0], card)

    def test_newer_version_rejected(self) -> None:
        with self.assertRaises(StateFormatError):
            AppState.from_dict({"version": 99, "cards": []})

    def test_invalid_root_rejected(self) -> None:
        with self.assertRaises(StateFormatError):
            AppState.from_dict([])

    def test_invalid_cards_skipped(self) -> None:
        state = AppState.from_dict(
            {
                "version": 1,
                "onboarding_dismissed": True,
                "cards": [None, "x", {"id": "ok", "title": "保留", "tasks": []}],
            }
        )
        self.assertTrue(state.onboarding_dismissed)
        self.assertEqual(len(state.cards), 1)
        self.assertEqual(state.cards[0].id, "ok")

    def test_round_trip(self) -> None:
        state = AppState(onboarding_dismissed=True)
        card = state.add_card("个人")
        assert card is not None
        card.add_task("跑五公里")
        restored = AppState.from_dict(state.to_dict())
        self.assertEqual(len(restored.cards), 1)
        self.assertTrue(restored.onboarding_dismissed)
        self.assertEqual(restored.cards[0].tasks[0].text, "跑五公里")

    def test_v1_state_defaults_to_solid_appearance(self) -> None:
        state = AppState.from_dict({"version": 1, "cards": []})
        self.assertEqual(state.version, 2)
        self.assertEqual(state.appearance, "solid")

    def test_glass_appearance_round_trip(self) -> None:
        state = AppState(appearance="glass")
        state.add_card("玻璃")
        payload = state.to_dict()
        self.assertEqual(payload["appearance"], "glass")
        restored = AppState.from_dict(payload)
        self.assertEqual(restored.appearance, "glass")

    def test_unknown_appearance_falls_back_to_solid(self) -> None:
        state = AppState.from_dict(
            {"version": 2, "appearance": "mirror", "cards": []}
        )
        self.assertEqual(state.appearance, "solid")


if __name__ == "__main__":
    unittest.main()
