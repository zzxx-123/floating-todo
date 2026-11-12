"""Fonts and deterministic two-line text fitting."""

from __future__ import annotations

import tkinter.font as tkfont
from functools import lru_cache

import customtkinter as ctk

from .constants import UI_FONT_FALLBACK, UI_FONT_FAMILIES


@lru_cache(maxsize=1)
def font_family() -> str:
    try:
        available = set(tkfont.families())
    except Exception:
        available = set()
    for family in UI_FONT_FAMILIES:
        if family in available:
            return family
    return UI_FONT_FALLBACK


@lru_cache(maxsize=32)
def ui_font(size: int, weight: str = "normal", overstrike: bool = False) -> ctk.CTkFont:
    return ctk.CTkFont(
        family=font_family(),
        size=int(size),
        weight=weight,
        overstrike=overstrike,
    )


def _take_line(text: str, font: ctk.CTkFont, width: int) -> tuple[str, str]:
    """Split one display line off ``text``, preferring a space boundary."""
    if font.measure(text) <= width:
        return text, ""
    low, high = 1, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if font.measure(text[:mid]) <= width:
            low = mid
        else:
            high = mid - 1
    cut = low
    space = text.rfind(" ", 0, cut + 1)
    if space >= max(1, int(cut * 0.55)):
        cut = space
    line = text[:cut].rstrip()
    rest = text[cut:].lstrip()
    if not line:
        line = text[:1]
        rest = text[1:].lstrip()
    return line, rest


def wrap_two_lines(text: str, font: ctk.CTkFont, width: int, max_lines: int = 2) -> str:
    """Wrap at most ``max_lines`` lines, adding an ellipsis if clipped.

    Tk's own wrapping is hard to measure, so the text is pre-wrapped with
    explicit newlines.  This keeps row heights and card heights predictable.
    """
    text = text.strip()
    if not text:
        return ""
    width = max(20, int(width))
    lines: list[str] = []
    rest = text
    for _ in range(max(1, max_lines)):
        if font.measure(rest) <= width:
            lines.append(rest)
            rest = ""
            break
        line, rest = _take_line(rest, font, width)
        lines.append(line)
        if not rest:
            break
    if rest and lines:
        last = lines[-1]
        while last and font.measure(last + "…") > width:
            last = last[:-1]
        lines[-1] = (last.rstrip() + "…") if last else "…"
    return "\n".join(lines[:max_lines])


def ellipsize(text: str, font: ctk.CTkFont, width: int) -> str:
    text = text.strip()
    if not text:
        return ""
    if font.measure(text) <= width:
        return text
    line, _rest = _take_line(text, font, max(20, int(width) - font.measure("…")))
    return (line.rstrip() + "…") if line else "…"


def line_count(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + 1
