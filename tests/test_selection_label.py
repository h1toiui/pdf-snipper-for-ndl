import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from widgets import (
    HANDLE_BOTTOM,
    HANDLE_BOTTOM_LEFT,
    HANDLE_BOTTOM_RIGHT,
    HANDLE_LEFT,
    HANDLE_RIGHT,
    HANDLE_TOP,
    HANDLE_TOP_LEFT,
    HANDLE_TOP_RIGHT,
    SELECTION_TWO_PAGE,
    SelectionLabel,
)


class SelectionLabelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = SelectionLabel()
        self.widget.setPixmap(QPixmap(1000, 1200))

    def test_spread_initial_selection_uses_eighty_percent_height(self):
        self.assertEqual(len(self.widget.selected_rects()), 1)
        self.assertEqual(self.widget.rect_p1.height(), 960)
        self.assertEqual(self.widget.rect_p1.center(), QPoint(499, 599))

    def test_two_page_fixed_ratio_creates_two_bounded_rects(self):
        self.widget.set_selection_mode(SELECTION_TWO_PAGE)
        self.widget.set_aspect_ratio(9 / 16)

        rects = self.widget.selected_rects()
        self.assertEqual(len(rects), 2)
        for rect in rects:
            self.assertAlmostEqual(rect.width() / rect.height(), 9 / 16, places=2)
            self.assertGreaterEqual(rect.x(), 0)
            self.assertGreaterEqual(rect.y(), 0)
            self.assertLessEqual(rect.x() + rect.width(), self.widget.image_width())
            self.assertLessEqual(rect.y() + rect.height(), self.widget.image_height())

    def test_setting_change_resets_selection_at_center(self):
        self.widget.rect_p1.translate(100, 100)

        self.widget.set_aspect_ratio(1 / 1.414)

        rect = self.widget.rect_p1
        self.assertEqual(len(self.widget.selected_rects()), 1)
        self.assertLessEqual(abs(rect.center().x() - 500), 1)
        self.assertLessEqual(abs(rect.center().y() - 600), 1)
        self.assertAlmostEqual(rect.width() / rect.height(), 1 / 1.414, places=2)

    def test_mode_change_immediately_creates_two_centered_rects(self):
        self.widget.rect_p1.translate(100, 100)

        self.widget.set_selection_mode(SELECTION_TWO_PAGE)

        self.assertEqual(len(self.widget.selected_rects()), 2)
        self.assertEqual(self.widget.rect_p1.center().y(), 599)
        self.assertEqual(self.widget.rect_p2.center().y(), 599)

    def test_all_corner_handles_are_drawn(self):
        handles = self.widget._handle_rects(self.widget.rect_p1)

        for handle in (
            HANDLE_TOP_LEFT,
            HANDLE_TOP_RIGHT,
            HANDLE_BOTTOM_LEFT,
            HANDLE_BOTTOM_RIGHT,
        ):
            self.assertIn(handle, handles)
        self.assertEqual(len(handles), 8)

    def test_fixed_ratio_corner_resize_ignores_pointer_x(self):
        self.widget.set_aspect_ratio(9 / 16)
        original = self.widget.rect_p1
        for handle in (
            HANDLE_TOP_LEFT,
            HANDLE_TOP_RIGHT,
            HANDLE_BOTTOM_LEFT,
            HANDLE_BOTTOM_RIGHT,
        ):
            with self.subTest(handle=handle):
                self.widget._active_handle = handle
                self.widget._drag_start_rect = original
                target_y = (
                    original.y() + 80
                    if handle in (HANDLE_TOP_LEFT, HANDLE_TOP_RIGHT)
                    else original.y() + original.height() - 80
                )

                left_result = self.widget._fixed_ratio_resized_rect(
                    QPoint(-500, target_y)
                )
                right_result = self.widget._fixed_ratio_resized_rect(
                    QPoint(1500, target_y)
                )

                self.assertEqual(left_result, right_result)
                self.assertAlmostEqual(
                    left_result.width() / left_result.height(),
                    9 / 16,
                    places=2,
                )

    def test_fixed_ratio_corner_resize_anchors_opposite_corner(self):
        self.widget.set_aspect_ratio(9 / 16)
        original = QRect(100, 100, 160, 284)
        self.widget._drag_start_rect = original

        anchors = {
            HANDLE_TOP_LEFT: (original.bottomRight(), "bottomRight"),
            HANDLE_TOP_RIGHT: (original.bottomLeft(), "bottomLeft"),
            HANDLE_BOTTOM_LEFT: (original.topRight(), "topRight"),
            HANDLE_BOTTOM_RIGHT: (original.topLeft(), "topLeft"),
        }

        for handle, (fixed_point, fixed_name) in anchors.items():
            with self.subTest(handle=handle):
                self.widget._active_handle = handle
                target_y = (
                    original.bottom() - 128
                    if handle in (HANDLE_TOP_LEFT, HANDLE_TOP_RIGHT)
                    else original.y() + 128
                )
                result = self.widget._fixed_ratio_resized_rect(
                    QPoint(original.x(), target_y)
                )
                if fixed_name == "bottomRight":
                    self.assertEqual(result.bottomRight(), fixed_point)
                elif fixed_name == "bottomLeft":
                    self.assertEqual(result.bottomLeft(), fixed_point)
                elif fixed_name == "topRight":
                    self.assertEqual(result.topRight(), fixed_point)
                else:
                    self.assertEqual(result.topLeft(), fixed_point)
                self.assertAlmostEqual(
                    result.width() / result.height(), 9 / 16, places=2
                )

    def test_fixed_ratio_side_handles_fix_horizontal_anchor(self):
        self.widget.set_aspect_ratio(9 / 16)
        original = QRect(100, 100, 160, 284)
        self.widget._drag_start_rect = original
        self.widget._drag_start = QPoint(original.left(), original.center().y())

        for handle in (HANDLE_LEFT, HANDLE_RIGHT):
            with self.subTest(handle=handle):
                self.widget._active_handle = handle
                target = QPoint(
                    (
                        original.left() - 20
                        if handle == HANDLE_LEFT
                        else original.right() + 20
                    ),
                    original.center().y(),
                )
                result = self.widget._fixed_ratio_resized_rect(target)
                if handle == HANDLE_LEFT:
                    self.assertEqual(result.right(), original.right())
                else:
                    self.assertEqual(result.left(), original.left())
                self.assertAlmostEqual(
                    result.width() / result.height(), 9 / 16, places=2
                )

    def test_fixed_ratio_two_page_resize_syncs_both_directions(self):
        self.widget.set_selection_mode(SELECTION_TWO_PAGE)
        self.widget.set_aspect_ratio(9 / 16)

        for active_name, other_name in (
            ("rect_p1", "rect_p2"),
            ("rect_p2", "rect_p1"),
        ):
            with self.subTest(active_name=active_name):
                setattr(self.widget, active_name, QRect(20, 30, 180, 320))
                setattr(self.widget, other_name, QRect(600, 100, 120, 213))
                self.widget._operation = "resize"
                self.widget._active_rect_name = active_name
                self.widget._active_handle = HANDLE_TOP_LEFT
                source_rect = QRect(0, 0, 120, 213)

                original_other = getattr(self.widget, other_name)
                self.widget._sync_other_rect_size(
                    source_rect.width(),
                    source_rect.height(),
                )

                other_rect = getattr(self.widget, other_name)
                self.assertEqual(other_rect.size(), source_rect.size())
                self.assertEqual(other_rect.bottomRight(), original_other.bottomRight())

    def test_fixed_ratio_two_page_resize_syncs_anchor_to_opposite_corner(self):
        self.widget.set_selection_mode(SELECTION_TWO_PAGE)
        self.widget.set_aspect_ratio(9 / 16)
        self.widget.rect_p1 = QRect(20, 30, 180, 320)
        self.widget.rect_p2 = QRect(600, 100, 120, 213)
        self.widget._operation = "resize"
        self.widget._active_rect_name = "rect_p1"
        source_rect = QRect(0, 0, 150, 266)

        other_rect = self.widget.rect_p2
        anchor_expectations = {
            HANDLE_TOP_LEFT: (other_rect.bottomRight(), "bottomRight"),
            HANDLE_TOP_RIGHT: (other_rect.bottomLeft(), "bottomLeft"),
            HANDLE_BOTTOM_LEFT: (other_rect.topRight(), "topRight"),
            HANDLE_BOTTOM_RIGHT: (other_rect.topLeft(), "topLeft"),
            HANDLE_LEFT: (QPoint(other_rect.right(), other_rect.center().y()), "right"),
            HANDLE_RIGHT: (QPoint(other_rect.left(), other_rect.center().y()), "left"),
            HANDLE_TOP: (
                QPoint(other_rect.center().x(), other_rect.bottom()),
                "bottom",
            ),
            HANDLE_BOTTOM: (QPoint(other_rect.center().x(), other_rect.top()), "top"),
        }

        for handle, (fixed_point, fixed_name) in anchor_expectations.items():
            with self.subTest(handle=handle):
                self.widget.rect_p2 = QRect(600, 100, 120, 213)
                self.widget._active_handle = handle
                self.widget._sync_other_rect_size(
                    source_rect.width(),
                    source_rect.height(),
                )
                other_rect = self.widget.rect_p2
                if fixed_name == "bottomRight":
                    self.assertEqual(other_rect.bottomRight(), fixed_point)
                elif fixed_name == "bottomLeft":
                    self.assertEqual(other_rect.bottomLeft(), fixed_point)
                elif fixed_name == "topRight":
                    self.assertEqual(other_rect.topRight(), fixed_point)
                elif fixed_name == "topLeft":
                    self.assertEqual(other_rect.topLeft(), fixed_point)
                elif fixed_name == "right":
                    self.assertEqual(other_rect.right(), fixed_point.x())
                    self.assertAlmostEqual(
                        other_rect.center().y(), fixed_point.y(), delta=1
                    )
                elif fixed_name == "left":
                    self.assertEqual(other_rect.left(), fixed_point.x())
                    self.assertAlmostEqual(
                        other_rect.center().y(), fixed_point.y(), delta=1
                    )
                elif fixed_name == "bottom":
                    self.assertEqual(other_rect.bottom(), fixed_point.y())
                    self.assertAlmostEqual(
                        other_rect.center().x(), fixed_point.x(), delta=1
                    )
                elif fixed_name == "top":
                    self.assertEqual(other_rect.top(), fixed_point.y())
                    self.assertAlmostEqual(
                        other_rect.center().x(), fixed_point.x(), delta=1
                    )
                self.assertEqual(other_rect.size(), source_rect.size())

    def test_fixed_ratio_two_page_resize_preserves_other_rect_fixed_corner(self):
        self.widget.set_selection_mode(SELECTION_TWO_PAGE)
        self.widget.set_aspect_ratio(9 / 16)

        self.widget.rect_p1 = QRect(20, 30, 180, 320)
        self.widget.rect_p2 = QRect(600, 100, 120, 213)
        self.widget._operation = "resize"
        self.widget._active_rect_name = "rect_p1"
        self.widget._active_handle = HANDLE_TOP_LEFT

        self.widget._sync_other_rect_size(150, 266)

        self.assertEqual(self.widget.rect_p2.bottomRight(), QPoint(719, 312))
        self.assertEqual(self.widget.rect_p2.size(), QSize(150, 266))

    def test_free_two_page_resize_does_not_request_size_sync(self):
        self.widget.set_selection_mode(SELECTION_TWO_PAGE)
        self.widget._operation = "resize"
        self.widget._active_rect_name = "rect_p1"

        self.assertFalse(self.widget._should_sync_two_page_size())

    def test_fixed_ratio_corner_handles_use_diagonal_cursors(self):
        self.widget.resize(1000, 1200)
        self.widget.set_aspect_ratio(9 / 16)
        widget_rect = self.widget._image_to_widget_rect(self.widget.rect_p1)
        expected = {
            HANDLE_TOP_LEFT: Qt.SizeFDiagCursor,
            HANDLE_TOP_RIGHT: Qt.SizeBDiagCursor,
            HANDLE_BOTTOM_LEFT: Qt.SizeBDiagCursor,
            HANDLE_BOTTOM_RIGHT: Qt.SizeFDiagCursor,
        }

        for handle, cursor_shape in expected.items():
            with self.subTest(handle=handle):
                point = self.widget._handle_rects(widget_rect)[handle].center()
                self.widget._update_cursor(point)
                self.assertEqual(self.widget.cursor().shape(), cursor_shape)

    def test_fixed_ratio_side_handles_use_horizontal_cursors(self):
        self.widget.resize(1000, 1200)
        self.widget.set_aspect_ratio(9 / 16)
        widget_rect = self.widget._image_to_widget_rect(self.widget.rect_p1)

        for handle in (HANDLE_LEFT, HANDLE_RIGHT):
            with self.subTest(handle=handle):
                point = self.widget._handle_rects(widget_rect)[handle].center()
                self.widget._update_cursor(point)
                self.assertEqual(self.widget.cursor().shape(), Qt.SizeHorCursor)

    def test_fixed_ratio_left_right_handles_follow_mouse_x(self):
        self.widget.set_aspect_ratio(9 / 16)
        original = QRect(100, 100, 160, 284)
        self.widget._drag_start_rect = original

        self.widget._active_handle = HANDLE_LEFT
        result_left = self.widget._fixed_ratio_resized_rect(
            QPoint(60, original.center().y())
        )
        self.assertEqual(result_left.left(), 60)
        self.assertAlmostEqual(
            result_left.width() / result_left.height(), 9 / 16, places=2
        )

        self.widget._active_handle = HANDLE_RIGHT
        result_right = self.widget._fixed_ratio_resized_rect(
            QPoint(290, original.center().y())
        )
        self.assertEqual(result_right.x() + result_right.width(), 290)
        self.assertAlmostEqual(
            result_right.width() / result_right.height(), 9 / 16, places=2
        )

    def test_fixed_ratio_side_resize_stops_at_image_edge(self):
        self.widget.set_aspect_ratio(9 / 16)
        original = QRect(100, 100, 160, 284)
        self.widget._drag_start_rect = original
        self.widget._active_handle = HANDLE_RIGHT

        result = self.widget._fixed_ratio_resized_rect(
            QPoint(self.widget.image_width() + 300, original.center().y())
        )

        self.assertEqual(result.left(), original.left())
        self.assertGreaterEqual(result.top(), 0)
        self.assertLessEqual(result.x() + result.width(), self.widget.image_width())
        self.assertLessEqual(result.y() + result.height(), self.widget.image_height())

    def test_fixed_ratio_side_sync_uses_same_anchor_logic_as_active_rect(self):
        self.widget.set_selection_mode(SELECTION_TWO_PAGE)
        self.widget.set_aspect_ratio(9 / 16)
        self.widget.rect_p1 = QRect(100, 100, 160, 284)
        self.widget.rect_p2 = QRect(600, 120, 160, 284)
        self.widget._drag_start_rect = QRect(self.widget.rect_p1)
        self.widget._operation = "resize"
        self.widget._active_rect_name = "rect_p1"
        self.widget._active_handle = HANDLE_LEFT

        active_rect = self.widget._fixed_ratio_resized_rect(
            QPoint(40, self.widget.rect_p1.center().y())
        )
        original_other = QRect(self.widget.rect_p2)

        self.widget._sync_other_rect_size(active_rect.width(), active_rect.height())

        self.assertEqual(self.widget.rect_p2.size(), active_rect.size())
        self.assertEqual(self.widget.rect_p2.right(), original_other.right())
        self.assertAlmostEqual(
            self.widget.rect_p2.center().y(),
            original_other.center().y(),
            delta=1,
        )

    def test_synced_fixed_ratio_resize_stops_at_smaller_limit(self):
        self.widget.set_selection_mode(SELECTION_TWO_PAGE)
        self.widget.set_aspect_ratio(9 / 16)
        self.widget.rect_p1 = QRect(100, 100, 160, 284)
        self.widget.rect_p2 = QRect(760, 120, 160, 284)
        self.widget._drag_start_rect = QRect(self.widget.rect_p1)
        self.widget._operation = "resize"
        self.widget._active_rect_name = "rect_p1"
        self.widget._active_handle = HANDLE_LEFT

        self.widget._apply_synced_fixed_ratio_resize(
            QPoint(-300, self.widget.rect_p1.center().y())
        )

        self.assertEqual(
            self.widget.rect_p1.x() + self.widget.rect_p1.width(),
            260,
        )
        self.assertEqual(
            self.widget.rect_p2.x() + self.widget.rect_p2.width(),
            920,
        )
        self.assertEqual(self.widget.rect_p1.size(), self.widget.rect_p2.size())
        self.assertGreaterEqual(self.widget.rect_p1.left(), 0)
        self.assertGreaterEqual(self.widget.rect_p2.left(), 0)


if __name__ == "__main__":
    unittest.main()
