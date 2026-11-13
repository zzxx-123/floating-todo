"""Windows integration helpers.

Nothing in this module imports Tk.  ``enable_dpi_awareness`` must be called
before any Tk/CustomTkinter import.
"""

from __future__ import annotations

import ctypes
import logging
import os
import time
import uuid
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import APP_NAME, WAKE_FILE_NAME, WINDOW_KEY

log = logging.getLogger(__name__)


# --------------------------------------------------------------------- dpi
def enable_dpi_awareness() -> str:
    """Make Tk see real screen pixels instead of a DPI-virtualized screen."""
    try:
        shcore = ctypes.windll.shcore
        # 2 == PROCESS_PER_MONITOR_DPI_AWARE
        result = shcore.SetProcessDpiAwareness(2)
        if result == 0:
            return "per-monitor"
    except Exception:
        pass
    try:
        # 1 == PROCESS_SYSTEM_DPI_AWARE (Win 8.1+ fallback)
        if ctypes.windll.shcore.SetProcessDpiAwareness(1) == 0:
            return "system"
    except Exception:
        pass
    try:
        if ctypes.windll.user32.SetProcessDPIAware():
            return "legacy"
    except Exception:
        pass
    return "none"


# ------------------------------------------------------------------ messages
MB_OK = 0x00000000
MB_YESNO = 0x00000004
MB_ICONERROR = 0x00000010
MB_ICONWARNING = 0x00000030
MB_ICONQUESTION = 0x00000020
MB_ICONINFORMATION = 0x00000040
MB_TOPMOST = 0x00040000
MB_SETFOREGROUND = 0x00010000
IDYES = 6


def show_error(text: str, title: str = APP_NAME) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, str(text), str(title), MB_OK | MB_ICONERROR | MB_TOPMOST | MB_SETFOREGROUND)
    except Exception:
        log.exception("MessageBoxW failed")


def show_info(text: str, title: str = APP_NAME) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, str(text), str(title), MB_OK | MB_ICONINFORMATION | MB_TOPMOST)
    except Exception:
        log.exception("MessageBoxW failed")


def confirm(text: str, title: str = APP_NAME) -> bool:
    try:
        result = ctypes.windll.user32.MessageBoxW(
            None, str(text), str(title), MB_YESNO | MB_ICONQUESTION | MB_TOPMOST | MB_SETFOREGROUND
        )
        return result == IDYES
    except Exception:
        log.exception("MessageBoxW failed")
        return False


# -------------------------------------------------------------------- mutex
ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    """A named Windows mutex.  Release it when the app exits."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.already_running = False
        self._handle: Any = None
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, False, name)
        error = ctypes.get_last_error()
        if not handle:
            raise OSError(f"无法创建单实例互斥量（错误 {error}）")
        self._handle = handle
        if error == ERROR_ALREADY_EXISTS:
            self.already_running = True

    def release(self) -> None:
        if self._handle:
            try:
                ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self._handle)
            except Exception:
                log.exception("CloseHandle failed")
            self._handle = None


# --------------------------------------------------------------- wake signal
def wake_stamp(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def signal_wake(data_dir: Path) -> bool:
    """Ask an already-running instance to surface its cards."""
    path = Path(data_dir) / WAKE_FILE_NAME
    try:
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
        tmp.write_text(f"{time.time_ns()}-{uuid.uuid4().hex}", encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError as exc:
        log.warning("Could not write wake signal %s: %s", path, exc)
        try:
            path.write_text(f"wake-{time.time_ns()}", encoding="utf-8")
            return True
        except OSError:
            return False


# --------------------------------------------------------------- window glue
def make_overlay(window: Any) -> None:
    """Turn a Toplevel into a borderless, chroma-keyed, always-on-top card."""
    window.overrideredirect(True)
    try:
        window.attributes("-transparentcolor", WINDOW_KEY)
    except Exception:
        log.debug("transparentcolor unavailable", exc_info=True)
    try:
        window.attributes("-topmost", True)
    except Exception:
        log.debug("topmost unavailable", exc_info=True)


def apply_topmost(window: Any, pinned: bool) -> None:
    try:
        window.attributes("-topmost", bool(pinned))
    except Exception:
        log.debug("could not set topmost", exc_info=True)
    if pinned:
        try:
            window.lift()
        except Exception:
            pass


# ----------------------------------------------------------- topmost popups
GA_ROOT = 2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
VK_LBUTTON = 0x01
VK_MENU = 0x12

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetAncestor.restype = wintypes.HWND
_user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
_user32.SetWindowPos.restype = wintypes.BOOL
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short


def raise_topmost(window: Any) -> bool:
    """Put a Tk top-level above other topmost windows.

    Tk's ``lift`` only reorders windows within Tk's own topmost group.  The
    cards are also topmost, so a popup needs a native SetWindowPos call to be
    reliably visible above the card the user just clicked.
    """
    try:
        hwnd = _user32.GetAncestor(wintypes.HWND(window.winfo_id()), GA_ROOT)
        if not hwnd:
            return False
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
        return bool(_user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, flags))
    except Exception:
        log.debug("Could not raise popup above topmost cards", exc_info=True)
        return False


def left_button_down() -> bool:
    """Return whether the physical left mouse button is currently held."""
    try:
        return bool(_user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
    except Exception:
        return False


def alt_down() -> bool:
    """Return whether Alt is physically held.

    Tk on Windows can report a Mod1 bit for synthetic mouse events even when
    Alt is not held, so modifier detection must consult the keyboard state.
    """
    try:
        return bool(_user32.GetAsyncKeyState(VK_MENU) & 0x8000)
    except Exception:
        return False


# ------------------------------------------------------------------ monitors
class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


@dataclass(frozen=True)
class Monitor:
    left: int
    top: int
    right: int
    bottom: int
    work_left: int
    work_top: int
    work_right: int
    work_bottom: int
    primary: bool = False

    @property
    def screen_rect(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)

    @property
    def work_rect(self) -> tuple[int, int, int, int]:
        return (self.work_left, self.work_top, self.work_right, self.work_bottom)


MONITORINFOF_PRIMARY = 0x00000001


def _enum_monitors() -> list[Monitor]:
    monitors: list[Monitor] = []
    try:
        user32 = ctypes.windll.user32
        MonitorEnumProc = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HMONITOR,
            wintypes.HDC,
            ctypes.POINTER(RECT),
            wintypes.LPARAM,
        )

        def callback(hmonitor: Any, _hdc: Any, _rect: Any, _data: Any) -> bool:
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
                m = info.rcMonitor
                w = info.rcWork
                monitors.append(
                    Monitor(
                        left=m.left,
                        top=m.top,
                        right=m.right,
                        bottom=m.bottom,
                        work_left=w.left,
                        work_top=w.top,
                        work_right=w.right,
                        work_bottom=w.bottom,
                        primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
                    )
                )
            return True

        proc = MonitorEnumProc(callback)
        user32.EnumDisplayMonitors(None, None, proc, 0)
    except Exception:
        log.warning("Monitor enumeration failed", exc_info=True)
    return monitors


class ScreenManager:
    """Physical-pixel monitor geometry with a safe single-screen fallback."""

    def __init__(self, root: Any) -> None:
        self.root = root
        self.monitors = _enum_monitors()
        if not self.monitors:
            width = int(root.winfo_screenwidth())
            height = int(root.winfo_screenheight())
            self.monitors = [
                Monitor(0, 0, width, height, 0, 0, width, height - 48, True)
            ]
        self._primary = next((m for m in self.monitors if m.primary), self.monitors[0])

    def primary_workarea(self) -> tuple[int, int, int, int]:
        return self._primary.work_rect

    def workarea_for_rect(self, rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        left, top, right, bottom = rect
        best: Monitor | None = None
        best_area = -1
        for monitor in self.monitors:
            ix = max(0, min(right, monitor.right) - max(left, monitor.left))
            iy = max(0, min(bottom, monitor.bottom) - max(top, monitor.top))
            area = ix * iy
            if area > best_area:
                best_area = area
                best = monitor
        return (best or self._primary).work_rect

    def ensure_rect_visible(self, x: int, y: int, width: int, height: int) -> tuple[int, int]:
        left, top, right, bottom = self.workarea_for_rect((x, y, x + width, y + height))
        max_x = right - width
        max_y = bottom - height
        if max_x < left:
            new_x = left
        else:
            new_x = min(max(x, left), max_x)
        if max_y < top:
            new_y = top
        else:
            new_y = min(max(y, top), max_y)
        return int(new_x), int(new_y)

    def cascade_position(
        self,
        card_width: int,
        card_height: int,
        anchor: tuple[int, int] | None = None,
        offset: int = 30,
    ) -> tuple[int, int]:
        if anchor is None:
            left, top, right, bottom = self.primary_workarea()
            x = right - card_width - offset
            y = top + offset * 2
        else:
            x = anchor[0] + offset
            y = anchor[1] + offset
        left, top, right, bottom = self.workarea_for_rect((x, y, x + card_width, y + card_height))
        if x + card_width > right or y + card_height > bottom:
            x = left + offset
            y = top + offset
        return self.ensure_rect_visible(x, y, card_width, card_height)

    def monitor_summary(self) -> str:
        return "; ".join(
            f"{'primary' if m.primary else 'screen'} {m.left},{m.top}-{m.right},{m.bottom} work={m.work_rect}"
            for m in self.monitors
        )


# ------------------------------------------------------------------ logging
def setup_logging(data_dir: Path, fallback_dir: Path | None = None) -> Path:
    candidates = [Path(data_dir)]
    if fallback_dir is not None:
        candidates.append(Path(fallback_dir))
    last_error: Exception | None = None
    for directory in candidates:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            log_path = directory / "app.log"
            handler = logging.FileHandler(log_path, encoding="utf-8", delay=False)
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            )
            root = logging.getLogger()
            root.setLevel(logging.INFO)
            root.addHandler(handler)
            return log_path
        except OSError as exc:
            last_error = exc
    logging.basicConfig(level=logging.INFO)
    log.warning("File logging unavailable: %s", last_error)
    return Path("")
