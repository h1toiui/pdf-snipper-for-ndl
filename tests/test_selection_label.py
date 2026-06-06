import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from widgets import (
    HANDLE_BOTTOM_LEFT,
    HANDLE_BOTTOM_RIGHT,
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
                source_rect = getattr(self.widget, active_name)

                self.widget._sync_other_rect_size(source_rect)

                other_rect = getattr(self.widget, other_name)
                self.assertEqual(other_rect.size(), source_rect.size())

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


if __name__ == "__main__":
    unittest.main()
