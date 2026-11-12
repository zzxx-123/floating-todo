from __future__ import annotations

import unittest
import uuid

from floating_todo.platform_win import SingleInstance


class SingleInstanceTests(unittest.TestCase):
    def test_mutex_blocks_a_second_copy_until_released(self) -> None:
        name = rf"Local\FloatingTodoCard_Test_{uuid.uuid4().hex}"
        first = SingleInstance(name)
        second = SingleInstance(name)
        try:
            self.assertFalse(first.already_running)
            self.assertTrue(second.already_running)
        finally:
            second.release()
            first.release()

    def test_mutex_can_be_reacquired_after_release(self) -> None:
        name = rf"Local\FloatingTodoCard_Test_{uuid.uuid4().hex}"
        first = SingleInstance(name)
        self.assertFalse(first.already_running)
        first.release()

        second = SingleInstance(name)
        try:
            self.assertFalse(second.already_running)
        finally:
            second.release()


if __name__ == "__main__":
    unittest.main()
