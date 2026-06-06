import unittest

from PySide6.QtCore import QRect

from pdf_processor import _qt_rect_to_pdf_rect


class PdfRectConversionTest(unittest.TestCase):
    def test_converts_full_qrect_extent(self):
        rect = _qt_rect_to_pdf_rect(
            QRect(150, 0, 150, 400),
            page_width=600,
            page_height=800,
            viewport_width=300,
            viewport_height=400,
        )

        self.assertEqual((rect.x0, rect.y0, rect.x1, rect.y1), (300, 0, 600, 800))


if __name__ == "__main__":
    unittest.main()
