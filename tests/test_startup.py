from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from floating_todo import startup


class StartupTests(unittest.TestCase):
    def test_command_line_quotes_pythonw_and_script(self) -> None:
        command = startup.command_line()
        self.assertIn("pythonw.exe", command)
        self.assertIn("app.pyw", command)
        self.assertTrue(command.startswith('"'))
        self.assertIn('" "', command)

    def test_registered_command_reads_run_key(self) -> None:
        key = MagicMock()
        with (
            patch.object(startup.winreg, "OpenKey", return_value=key),
            patch.object(startup.winreg, "QueryValueEx", return_value=("cmd", 1)),
        ):
            self.assertEqual(startup.registered_command(), "cmd")
        key.__enter__.assert_called_once()
        key.__exit__.assert_called_once()

    def test_missing_run_key_is_disabled(self) -> None:
        with patch.object(startup.winreg, "OpenKey", side_effect=FileNotFoundError):
            self.assertIsNone(startup.registered_command())
            self.assertFalse(startup.is_enabled())

    def test_registry_access_error_is_disabled(self) -> None:
        with patch.object(startup.winreg, "OpenKey", side_effect=PermissionError):
            self.assertIsNone(startup.registered_command())

    def test_enable_writes_current_command(self) -> None:
        key = MagicMock()
        key.__enter__.return_value = key
        with (
            patch.object(startup.winreg, "CreateKey", return_value=key),
            patch.object(startup.winreg, "SetValueEx") as set_value,
            patch.object(startup, "command_line", return_value='"py" "app.pyw"'),
        ):
            startup.set_enabled(True)
        set_value.assert_called_once_with(
            key, startup.VALUE_NAME, 0, startup.winreg.REG_SZ, '"py" "app.pyw"'
        )

    def test_disable_deletes_value(self) -> None:
        key = MagicMock()
        key.__enter__.return_value = key
        with (
            patch.object(startup.winreg, "OpenKey", return_value=key),
            patch.object(startup.winreg, "DeleteValue") as delete_value,
        ):
            startup.set_enabled(False)
        delete_value.assert_called_once_with(key, startup.VALUE_NAME)

    def test_disable_is_idempotent(self) -> None:
        with patch.object(startup.winreg, "OpenKey", side_effect=FileNotFoundError):
            startup.set_enabled(False)


if __name__ == "__main__":
    unittest.main()
