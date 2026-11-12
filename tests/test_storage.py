from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from floating_todo.models import AppState
from floating_todo.storage import StateStore


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.store = StateStore(self.dir)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _state(self) -> AppState:
        state = AppState()
        card = state.ensure_card()
        card.title = "测试"
        card.add_task("第一个")
        return state

    def test_load_new(self) -> None:
        result = self.store.load()
        self.assertEqual(result.status, "new")
        self.assertEqual(result.state.cards, [])

    def test_save_and_load_round_trip(self) -> None:
        state = self._state()
        self.store.save(state)
        self.assertTrue(self.store.path.exists())
        result = self.store.load()
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.state.cards[0].title, "测试")
        self.assertEqual(result.state.cards[0].tasks[0].text, "第一个")

    def test_backup_created_on_second_save(self) -> None:
        self.store.save(self._state())
        state = self._state()
        state.cards[0].title = "第二版"
        self.store.save(state)
        self.assertTrue(self.store.backup_path.exists())
        backup = json.loads(self.store.backup_path.read_text(encoding="utf-8"))
        self.assertEqual(backup["cards"][0]["title"], "测试")

    def test_recovers_from_backup_when_main_is_corrupt(self) -> None:
        self.store.save(self._state())
        second = self._state()
        second.cards[0].title = "第二版"
        self.store.save(second)
        self.store.path.write_text("{ not json", encoding="utf-8")
        result = self.store.load()
        self.assertEqual(result.status, "recovered")
        self.assertEqual(result.state.cards[0].title, "测试")
        self.assertTrue(list(self.dir.glob("state.corrupt-*.json")))

    def test_fresh_when_both_broken(self) -> None:
        self.dir.mkdir(exist_ok=True)
        self.store.path.write_text("broken", encoding="utf-8")
        self.store.backup_path.write_text("also broken", encoding="utf-8")
        result = self.store.load()
        self.assertEqual(result.status, "fresh")
        self.assertEqual(result.state.cards, [])
        self.assertEqual(len(list(self.dir.glob("state.corrupt-*.json"))), 2)

    def test_corrupt_main_does_not_destroy_good_backup(self) -> None:
        self.store.save(self._state())
        self.store.save(self._state())
        good_backup = self.store.backup_path.read_bytes()
        self.store.path.write_text("broken", encoding="utf-8")
        self.store.save(self._state())
        self.assertEqual(self.store.backup_path.read_bytes(), good_backup)

    def test_unicode_persisted(self) -> None:
        state = self._state()
        state.cards[0].title = "工作 · 本周"
        state.cards[0].tasks[0].text = "写一份中文周报 ✅"
        self.store.save(state)
        raw = self.store.path.read_text(encoding="utf-8")
        self.assertIn("工作 · 本周", raw)
        self.assertIn("写一份中文周报 ✅", raw)

    def test_atomic_temp_file_cleaned_up(self) -> None:
        self.store.save(self._state())
        self.assertEqual(list(self.dir.glob("*.tmp-*")), [])


if __name__ == "__main__":
    unittest.main()
