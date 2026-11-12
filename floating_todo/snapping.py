"""Pure geometry for magnetic card snapping and docking groups.

All coordinates are physical screen pixels.  The module deliberately has no
Tk imports so it can be tested without a display.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable, Sequence

Rect = tuple[int, int, int, int]  # left, top, right, bottom


@dataclass(frozen=True)
class SnapResult:
    x: int
    y: int
    dx: int
    dy: int
    target_ids: tuple[str, ...] = ()

    @property
    def moved(self) -> bool:
        return self.dx != 0 or self.dy != 0


def rect_for(x: int, y: int, width: int, height: int) -> Rect:
    return (int(x), int(y), int(x) + int(width), int(y) + int(height))


def rect_width(rect: Rect) -> int:
    return rect[2] - rect[0]


def rect_height(rect: Rect) -> int:
    return rect[3] - rect[1]


def group_bounds(rects: Iterable[Rect]) -> Rect:
    rects = list(rects)
    if not rects:
        return (0, 0, 0, 0)
    return (
        min(rect[0] for rect in rects),
        min(rect[1] for rect in rects),
        max(rect[2] for rect in rects),
        max(rect[3] for rect in rects),
    )


def _range_gap(a1: int, a2: int, b1: int, b2: int) -> int:
    """Positive gap between 1-D ranges, zero when they overlap."""
    if a2 < b1:
        return b1 - a2
    if b2 < a1:
        return a1 - b2
    return 0


def _perpendicular_close(a1: int, a2: int, b1: int, b2: int, threshold: int) -> bool:
    return _range_gap(a1, a2, b1, b2) <= threshold


def _overlap_1d(a1: int, a2: int, b1: int, b2: int) -> int:
    return max(0, min(a2, b2) - max(a1, b1))


def snap_move(
    x: int,
    y: int,
    width: int,
    height: int,
    others: Sequence[tuple[str, Rect]],
    workarea: Rect,
    gap: int,
    threshold: int,
) -> SnapResult:
    """Snap a dragged rectangle to neighbouring cards and monitor edges.

    A candidate is considered only when the two rectangles are close along the
    perpendicular axis.  The closest candidate on each axis wins.  The final
    position is clamped into ``workarea``.
    """
    width = max(1, int(width))
    height = max(1, int(height))
    gap = max(0, int(gap))
    threshold = max(1, int(threshold))
    best_dx: int | None = None
    best_dy: int | None = None
    best_x_targets: set[str] = set()
    best_y_targets: set[str] = set()

    def consider_x(candidate: int, target: str | None) -> None:
        nonlocal best_dx, best_x_targets
        delta = int(candidate) - x
        if abs(delta) > threshold:
            return
        if best_dx is None or abs(delta) < abs(best_dx):
            best_dx = delta
            best_x_targets = {target} if target else set()
        elif abs(delta) == abs(best_dx) and target:
            best_x_targets.add(target)

    def consider_y(candidate: int, target: str | None) -> None:
        nonlocal best_dy, best_y_targets
        delta = int(candidate) - y
        if abs(delta) > threshold:
            return
        if best_dy is None or abs(delta) < abs(best_dy):
            best_dy = delta
            best_y_targets = {target} if target else set()
        elif abs(delta) == abs(best_dy) and target:
            best_y_targets.add(target)

    for target_id, other in others:
        ox1, oy1, ox2, oy2 = other
        near_vertically = _perpendicular_close(y, y + height, oy1, oy2, threshold)
        near_horizontally = _perpendicular_close(x, x + width, ox1, ox2, threshold)

        if near_vertically:
            consider_x(ox1, target_id)  # align left edges
            consider_x(ox2 - width, target_id)  # align right edges
            consider_x(ox2 + gap, target_id)  # dock to the right
            consider_x(ox1 - gap - width, target_id)  # dock to the left

        if near_horizontally:
            consider_y(oy1, target_id)  # align top edges
            consider_y(oy2 - height, target_id)  # align bottom edges
            consider_y(oy2 + gap, target_id)  # dock below
            consider_y(oy1 - gap - height, target_id)  # dock above

    wa_left, wa_top, wa_right, wa_bottom = workarea
    consider_x(wa_left, None)
    consider_x(wa_right - width, None)
    consider_y(wa_top, None)
    consider_y(wa_bottom - height, None)

    snapped_x = x + best_dx if best_dx is not None else x
    snapped_y = y + best_dy if best_dy is not None else y
    max_x = max(wa_left, wa_right - width)
    max_y = max(wa_top, wa_bottom - height)
    final_x = min(max(snapped_x, wa_left), max_x)
    final_y = min(max(snapped_y, wa_top), max_y)
    return SnapResult(
        x=int(final_x),
        y=int(final_y),
        dx=int(final_x - x),
        dy=int(final_y - y),
        target_ids=tuple(sorted(best_x_targets | best_y_targets)),
    )


def cards_touch(a: Rect, b: Rect, gap: int, tolerance: int) -> bool:
    """True when two cards are docked side-by-side or stacked."""
    allowed = max(0, int(gap)) + max(0, int(tolerance))
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    x_gap = _range_gap(ax1, ax2, bx1, bx2)
    y_gap = _range_gap(ay1, ay2, by1, by2)
    vertical_overlap = _overlap_1d(ay1, ay2, by1, by2)
    horizontal_overlap = _overlap_1d(ax1, ax2, bx1, bx2)
    side_by_side = x_gap <= allowed and vertical_overlap > 0
    stacked = y_gap <= allowed and horizontal_overlap > 0
    return bool(side_by_side or stacked)


def find_group(
    start_id: str,
    rects: dict[str, Rect],
    gap: int,
    tolerance: int,
) -> tuple[str, ...]:
    """Return the connected docking group containing ``start_id``."""
    if start_id not in rects:
        return ()
    seen = {start_id}
    queue: deque[str] = deque([start_id])
    while queue:
        current = queue.popleft()
        for other_id, rect in rects.items():
            if other_id in seen:
                continue
            if cards_touch(rects[current], rect, gap, tolerance):
                seen.add(other_id)
                queue.append(other_id)
    return tuple(card_id for card_id in rects if card_id in seen)


def clamp_delta_to_workarea(
    x: int, y: int, width: int, height: int, dx: int, dy: int, workarea: Rect
) -> tuple[int, int]:
    """Limit a group translation so its bounds stay inside the work area."""
    left, top, right, bottom = workarea
    new_x = x + dx
    new_y = y + dy
    if new_x < left:
        dx += left - new_x
    if new_y < top:
        dy += top - new_y
    if new_x + width > right:
        dx -= new_x + width - right
    if new_y + height > bottom:
        dy -= new_y + height - bottom
    return int(dx), int(dy)
