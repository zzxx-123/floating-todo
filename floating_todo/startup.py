"""Windows "start with Windows" integration (HKCU Run key)."""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "FloatingTodoCard"


def _pythonw() -> Path:
    executable = Path(sys.executable)
    pythonw = executable.with_name("pythonw.exe")
    return pythonw if pythonw.exists() else executable


def app_script() -> Path:
    return Path(__file__).resolve().parent.parent / "app.pyw"


def command_line() -> str:
    return f'"{_pythonw()}" "{app_script()}"'


def registered_command() -> str | None:
    """Return the currently registered command, or None if disabled."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
    except (FileNotFoundError, OSError):
        return None
    return value if isinstance(value, str) else None


def is_enabled() -> bool:
    return registered_command() is not None


def set_enabled(enabled: bool) -> None:
    if enabled:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command_line())
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        pass
