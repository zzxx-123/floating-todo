"""Pure geometry helpers for arranging a magnetic card group in a grid."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from .snapping import Rect


@dataclass(frozen=True)
class LayoutItem:
    card_id: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class GroupLayout:
    positions: dict[str, tuple[int, int]]
    columns: int
    rows: int
    gap: int


def _column_count(n: int, cell_width: int, workarea: Rect, gap: int) -> int:
    """Pick a small, predictable column count that also fits the screen."""
    if n <= 1:
        return 1
    available = max(1, workarea[2] - workarea[0])
    max_fit = max(1, (available + gap) // max(1, cell_width + gap))
    if n == 2:
        preferred = 2
    elif n == 3:
        preferred = 3
    elif n == 4:
        preferred = 2
    else:
        preferred = 3
    return max(1, min(n, preferred, max_fit))


def arrange_group(items: Iterable[LayoutItem], workarea: Rect, gap: int) -> GroupLayout:
    """Arrange items in a centered row-major grid.

    Cards are sorted by their current visual order (top-to-bottom, left-to-right),
    which keeps the arrangement stable after the user drags a card to a new
    position. Column widths are unified to the widest card so the resulting
    block has a clean outer silhouette.
    """
    ordered = sorted(items, key=lambda item: (item.y, item.x, item.card_id))
    n = len(ordered)
    if n == 0:
        return GroupLayout({}, 0, 0, gap)
    if n == 1:
        card = ordered[0]
        return GroupLayout({card.card_id: (card.x, card.y)}, 1, 1, gap)

    cell_width = max(item.width for item in ordered)
    columns = _column_count(n, cell_width, workarea, gap)
    rows = math.ceil(n / columns)
    row_heights: list[int] = []
    for row in range(rows):
        row_items = ordered[row * columns : (row + 1) * columns]
        row_heights.append(max(item.height for item in row_items))

    total_width = columns * cell_width + max(0, columns - 1) * gap
    total_height = sum(row_heights) + max(0, rows - 1) * gap
    current_left = min(item.x for item in ordered)
    current_top = min(item.y for item in ordered)
    current_right = max(item.x + item.width for item in ordered)
    current_bottom = max(item.y + item.height for item in ordered)
    desired_left = round((current_left + current_right - total_width) / 2)
    desired_top = round((current_top + current_bottom - total_height) / 2)

    left = max(workarea[0], min(desired_left, workarea[2] - total_width))
    top = max(workarea[1], min(desired_top, workarea[3] - total_height))

    positions: dict[str, tuple[int, int]] = {}
    row_top = top
    for row in range(rows):
        row_items = ordered[row * columns : (row + 1) * columns]
        for column, item in enumerate(row_items):
            cell_left = left + column * (cell_width + gap)
            x = cell_left + (cell_width - item.width) // 2
            y = row_top
            positions[item.card_id] = (x, y)
        row_top += row_heights[row] + gap

    return GroupLayout(positions, columns, rows, gap)
