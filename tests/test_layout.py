from __future__ import annotations

import unittest

from floating_todo.layout import LayoutItem, arrange_group


WORKAREA = (0, 0, 2560, 1600)


def items(count: int, width: int = 400, height: int = 300) -> list[LayoutItem]:
    return [
        LayoutItem(f"c{index}", 100 + index * 30, 100 + index * 20, width, height)
        for index in range(count)
    ]


class ArrangeGroupTests(unittest.TestCase):
    def test_single_card_keeps_position(self) -> None:
        layout = arrange_group([LayoutItem("a", 10, 20, 400, 300)], WORKAREA, 10)
        self.assertEqual(layout.positions, {"a": (10, 20)})
        self.assertEqual((layout.columns, layout.rows), (1, 1))

    def test_two_cards_are_side_by_side(self) -> None:
        layout = arrange_group(items(2), WORKAREA, 10)
        self.assertEqual((layout.columns, layout.rows), (2, 1))
        (x1, y1), (x2, y2) = (layout.positions["c0"], layout.positions["c1"])
        self.assertEqual(x2 - x1, 410)
        self.assertEqual(y1, y2)

    def test_three_cards_use_three_columns_when_they_fit(self) -> None:
        layout = arrange_group(items(3, width=300), WORKAREA, 10)
        self.assertEqual((layout.columns, layout.rows), (3, 1))

    def test_three_wide_cards_fall_back_to_two_columns(self) -> None:
        layout = arrange_group(items(3, width=900), (0, 0, 1900, 1600), 10)
        self.assertEqual((layout.columns, layout.rows), (2, 2))

    def test_four_cards_form_a_two_by_two_grid(self) -> None:
        layout = arrange_group(items(4), WORKAREA, 10)
        self.assertEqual((layout.columns, layout.rows), (2, 2))
        ys = {layout.positions[f"c{index}"][1] for index in range(4)}
        self.assertEqual(len(ys), 2)

    def test_five_cards_use_three_columns(self) -> None:
        layout = arrange_group(items(5, width=300), WORKAREA, 10)
        self.assertEqual(layout.columns, 3)
        self.assertEqual(layout.rows, 2)

    def test_layout_stays_inside_workarea(self) -> None:
        layout = arrange_group(
            [
                LayoutItem("a", 50, 50, 400, 300),
                LayoutItem("b", 70, 70, 400, 300),
                LayoutItem("c", 90, 90, 400, 300),
            ],
            (0, 0, 1000, 700),
            10,
        )
        for x, y in layout.positions.values():
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + 400, 1000)
            self.assertLessEqual(y + 300, 700)

    def test_order_follows_current_visual_position(self) -> None:
        layout = arrange_group(
            [
                LayoutItem("bottom", 0, 500, 300, 200),
                LayoutItem("top", 0, 0, 300, 200),
            ],
            WORKAREA,
            10,
        )
        top_x, top_y = layout.positions["top"]
        bottom_x, bottom_y = layout.positions["bottom"]
        self.assertEqual(top_y, bottom_y)
        self.assertLess(top_x, bottom_x)

    def test_cards_in_one_row_are_top_aligned(self) -> None:
        layout = arrange_group(
            [
                LayoutItem("tall", 100, 100, 400, 500),
                LayoutItem("short", 600, 100, 400, 300),
            ],
            WORKAREA,
            10,
        )
        self.assertEqual(
            layout.positions["tall"][1],
            layout.positions["short"][1],
        )


if __name__ == "__main__":
    unittest.main()
