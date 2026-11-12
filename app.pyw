"""Desktop entry point for the floating todo cards.

Run this file with ``pythonw.exe`` (no console window).  DPI awareness must be
enabled before CustomTkinter/Tk is imported, otherwise Windows virtualizes the
screen and the cards become blurry.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from floating_todo.platform_win import enable_dpi_awareness  # noqa: E402

enable_dpi_awareness()

from floating_todo.app import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
