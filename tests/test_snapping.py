from __future__ import annotations

import unittest

from floating_todo.snapping import (
    cards_touch,
    clamp_delta_to_workarea,
    find_group,
    group_bounds,
    rect_for,
    snap_move,
)

WORKAREA = (0, 0, 1920, 1040)
GAP = 10
THRESHOLD = 14


class SnapMoveTests(unittest.TestCase):
    def test_docks_to_right_of_other_card_with_gap(self) -> None:
        other = ("other", rect_for(400, 200, 300, 200))
        result = snap_move(703, 205, 300, 200, [other], WORKAREA, GAP, THRESHOLD)
        self.assertEqual(result.x, 710)
        self.assertEqual(result.dx, 7)
        self.assertEqual(result.y, 200)
        self.assertIn("other", result.target_ids)

    def test_docks_below_other_card_with_gap(self) -> None:
        other = ("other", rect_for(200, 200, 300, 180))
        result = snap_move(196, 385, 300, 200, [other], WORKAREA, GAP, THRESHOLD)
        self.assertEqual(result.x, 200)
        self.assertEqual(result.y, 390)
        self.assertIn("other", result.target_ids)

    def test_aligns_left_edges(self) -> None:
        other = ("other", rect_for(400, 200, 300, 200))
        result = snap_move(406, 390, 300, 200, [other], WORKAREA, GAP, THRESHOLD)
        self.assertEqual(result.x, 400)

    def test_no_snap_outside_threshold(self) -> None:
        other = ("other", rect_for(400, 200, 300, 200))
        result = snap_move(734, 500, 300, 200, [other], WORKAREA, GAP, THRESHOLD)
        self.assertEqual((result.x, result.y), (734, 500))
        self.assertEqual(result.target_ids, ())

    def test_no_snap_when_vertically_far_away(self) -> None:
        other = ("other", rect_for(400, 0, 300, 200))
        result = snap_move(704, 800, 300, 200, [other], WORKAREA, GAP, THRESHOLD)
        self.assertEqual(result.x, 704)
        self.assertEqual(result.target_ids, ())

    def test_snaps_to_workarea_edges(self) -> None:
        result = snap_move(8, 830, 300, 200, [], WORKAREA, GAP, THRESHOLD)
        self.assertEqual(result.x, 0)
        self.assertEqual(result.y, 840)

    def test_clamps_oversized_card(self) -> None:
        result = snap_move(-200, -100, 2200, 1200, [], WORKAREA, GAP, THRESHOLD)
        self.assertEqual(result.x, 0)
        self.assertEqual(result.y, 0)

    def test_group_bounds(self) -> None:
        self.assertEqual(
            group_bounds([rect_for(10, 20, 100, 50), rect_for(150, 90, 80, 40)]),
            (10, 20, 230, 130),
        )


class DockGroupTests(unittest.TestCase):
    def test_touching_side_by_side(self) -> None:
        a = rect_for(0, 0, 300, 200)
        b = rect_for(310, 0, 300, 200)
        self.assertTrue(cards_touch(a, b, 10, 2))
        group = find_group("a", {"a": a, "b": b, "c": rect_for(900, 900, 300, 200)}, 10, 2)
        self.assertEqual(set(group), {"a", "b"})

    def test_diagonal_corner_is_not_docked(self) -> None:
        a = rect_for(0, 0, 300, 200)
        b = rect_for(310, 210, 300, 200)
        self.assertFalse(cards_touch(a, b, 10, 2))

    def test_transitive_group(self) -> None:
        a = rect_for(0, 0, 300, 200)
        b = rect_for(310, 0, 300, 200)
        c = rect_for(620, 0, 300, 200)
        group = find_group("b", {"a": a, "b": b, "c": c, "d": rect_for(0, 500, 300, 200)}, 10, 2)
        self.assertEqual(set(group), {"a", "b", "c"})

    def test_stacked_group(self) -> None:
        a = rect_for(0, 0, 300, 200)
        b = rect_for(0, 210, 300, 200)
        self.assertTrue(cards_touch(a, b, 10, 2))

    def test_unknown_start(self) -> None:
        self.assertEqual(find_group("missing", {}, 10, 2), ())

    def test_clamp_delta(self) -> None:
        dx, dy = clamp_delta_to_workarea(100, 100, 300, 200, -200, -300, WORKAREA)
        self.assertEqual((dx, dy), (-100, -100))
        dx, dy = clamp_delta_to_workarea(1500, 800, 300, 200, 500, 500, WORKAREA)
        self.assertEqual((dx, dy), (120, 40))


if __name__ == "__main__":
    unittest.main()
