from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel


SELECTION_SPREAD = "spread"
SELECTION_TWO_PAGE = "two_page"

HANDLE_LEFT = "left"
HANDLE_RIGHT = "right"
HANDLE_TOP = "top"
HANDLE_BOTTOM = "bottom"
HANDLE_TOP_LEFT = "top_left"
HANDLE_TOP_RIGHT = "top_right"
HANDLE_BOTTOM_LEFT = "bottom_left"
HANDLE_BOTTOM_RIGHT = "bottom_right"

HANDLE_SIZE = 10
MIN_SELECTION_SIZE = 12


class SelectionLabel(QLabel):
    """画像上で移動・リサイズ可能な切り抜き矩形を管理する。"""

    def __init__(self):
        super().__init__()
        self._pixmap = QPixmap()
        self.zoom = 1.0
        self.rect_p1 = QRect()
        self.rect_p2 = QRect()
        self.selection_mode = SELECTION_SPREAD
        self.aspect_ratio = None
        self.source_aspect_ratio = 1.0
        self._operation = None
        self._active_rect_name = None
        self._active_handle = None
        self._drag_start = QPoint()
        self._drag_start_rect = QRect()
        self.setMouseTracking(True)

    def setPixmap(self, pixmap):
        """プレビュー画像を設定し、選択枠を新しい画像寸法へ追従させる。"""
        old_width = self._pixmap.width()
        old_height = self._pixmap.height()
        self._pixmap = QPixmap(pixmap)
        self.zoom = 1.0

        if old_width > 0 and old_height > 0:
            self.rect_p1 = self._scaled_rect(
                self.rect_p1,
                old_width,
                old_height,
                self._pixmap.width(),
                self._pixmap.height(),
            )
            self.rect_p2 = self._scaled_rect(
                self.rect_p2,
                old_width,
                old_height,
                self._pixmap.width(),
                self._pixmap.height(),
            )
        if not self._pixmap.isNull() and not self.selected_rects():
            self._create_initial_selection()
        self.update()

    def pixmap(self):
        """現在のプレビュー画像を返す。"""
        return self._pixmap

    def clear(self):
        """プレビュー画像を消す。"""
        self._pixmap = QPixmap()
        self._reset_operation()
        self.update()

    def image_width(self):
        """プレビュー画像の元幅を返す。"""
        return max(1, self._pixmap.width())

    def image_height(self):
        """プレビュー画像の元高さを返す。"""
        return max(1, self._pixmap.height())

    def set_selection_mode(self, mode):
        """見開きまたは2Pへ切り替え、既存の選択枠を破棄する。"""
        if mode not in (SELECTION_SPREAD, SELECTION_TWO_PAGE):
            raise ValueError(f"Unsupported selection mode: {mode}")
        if self.selection_mode == mode:
            return
        self.selection_mode = mode
        self._reset_selection()

    def set_aspect_ratio(self, ratio):
        """固定アスペクト比を設定し、既存の選択枠を破棄する。"""
        if ratio is not None and ratio <= 0:
            raise ValueError("Aspect ratio must be positive")
        if self.aspect_ratio == ratio:
            return
        self.aspect_ratio = ratio
        self._reset_selection()

    def set_source_aspect_ratio(self, ratio):
        """元PDFの1ページ目から取得した幅/高さ比を保持する。"""
        if ratio > 0:
            self.source_aspect_ratio = ratio

    def mousePressEvent(self, event):
        """ハンドラー、枠移動、または新規枠作成の操作を開始する。"""
        if event.button() != Qt.LeftButton or self._pixmap.isNull():
            return

        image_pos = self._widget_to_image_pos(event.pos())
        if image_pos is None:
            return

        target = self._hit_test(event.pos())
        if target is None:
            return

        rect_name, handle = target
        self._active_rect_name = rect_name
        self._active_handle = handle
        self._drag_start = image_pos
        self._drag_start_rect = QRect(self._rect_by_name(rect_name))
        self._operation = "resize" if handle is not None else "move"

    def mouseMoveEvent(self, event):
        """操作中の選択枠を更新し、未操作時はカーソル形状を切り替える。"""
        if self._operation is None:
            self._update_cursor(event.pos())
            return
        if not event.buttons() & Qt.LeftButton:
            self._reset_operation()
            return

        image_pos = self._widget_to_image_pos(event.pos(), clamp=True)
        if image_pos is None:
            return

        if self._operation == "move":
            rect = self._moved_rect(image_pos)
        elif self.aspect_ratio is None:
            rect = self._freely_resized_rect(image_pos)
        else:
            rect = self._fixed_ratio_resized_rect(image_pos)

        self._set_rect_by_name(self._active_rect_name, rect)
        if self._should_sync_two_page_size():
            self._sync_other_rect_size(rect)
        self.update()

    def mouseReleaseEvent(self, event):
        """移動・リサイズ操作を終了する。"""
        if event.button() == Qt.LeftButton:
            self._reset_operation()
            self._update_cursor(event.pos())

    def wheelEvent(self, event):
        """マウスホイールでプレビュー画像を拡大縮小する。"""
        if self._pixmap.isNull():
            return

        step = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.zoom = min(6.0, max(0.25, self.zoom * step))
        self.update()

    def clear_selection(self):
        """保持している切り抜き矩形をすべて消す。"""
        self.rect_p1 = QRect()
        self.rect_p2 = QRect()
        self._reset_operation()
        self.update()

    def selected_rects(self):
        """現在の選択モードで有効な切り抜き矩形を返す。"""
        if self.selection_mode == SELECTION_SPREAD:
            return [self.rect_p1] if not self.rect_p1.isNull() else []
        return [rect for rect in (self.rect_p1, self.rect_p2) if not rect.isNull()]

    def paintEvent(self, event):
        """プレビュー画像、選択枠、ラベル、ハンドラーを描画する。"""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#eeeeee"))
        painter.setPen(QPen(QColor("#cccccc"), 2))
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))

        if self._pixmap.isNull():
            return

        painter.drawPixmap(self._display_rect(), self._pixmap)
        self._draw_selection(painter, self.rect_p1, QColor("#e00000"), self._page1_label())
        if self.selection_mode == SELECTION_TWO_PAGE:
            self._draw_selection(painter, self.rect_p2, QColor("#0057d9"), "Page2")

    def _create_initial_selection(self):
        """現在の設定に従う選択枠を画像中央へ生成する。"""
        image_width = self.image_width()
        image_height = self.image_height()
        gap = max(8, round(image_width * 0.02))

        if self.selection_mode == SELECTION_SPREAD:
            width, height = self._initial_size(image_width, image_height, image_width)
            self.rect_p1 = self._centered_rect(width, height, image_width / 2)
            self.rect_p2 = QRect()
            return

        available_width = max(MIN_SELECTION_SIZE, (image_width - gap) / 2)
        width, height = self._initial_size(image_width, image_height, available_width)
        total_width = width * 2 + gap
        left = (image_width - total_width) / 2
        top = (image_height - height) / 2
        self.rect_p1 = QRect(round(left), round(top), round(width), round(height))
        self.rect_p2 = QRect(
            round(left + width + gap),
            round(top),
            round(width),
            round(height),
        )

    def _initial_size(self, image_width, image_height, available_width):
        height = image_height * 0.8
        if self.aspect_ratio is None:
            width = min(image_width * 0.8, available_width)
        else:
            width = height * self.aspect_ratio
            if width > available_width:
                width = available_width
                height = width / self.aspect_ratio
        return max(MIN_SELECTION_SIZE, width), max(MIN_SELECTION_SIZE, height)

    def _centered_rect(self, width, height, center_x):
        left = center_x - width / 2
        top = (self.image_height() - height) / 2
        return QRect(round(left), round(top), round(width), round(height))

    def _moved_rect(self, image_pos):
        dx = image_pos.x() - self._drag_start.x()
        dy = image_pos.y() - self._drag_start.y()
        rect = self._drag_start_rect.translated(dx, dy)
        x = min(max(0, rect.x()), self.image_width() - rect.width())
        y = min(max(0, rect.y()), self.image_height() - rect.height())
        return QRect(x, y, rect.width(), rect.height())

    def _freely_resized_rect(self, image_pos):
        x0, y0, x1, y1 = self._rect_bounds(self._drag_start_rect)
        x = image_pos.x()
        y = image_pos.y()

        if self._active_handle in (HANDLE_LEFT, HANDLE_TOP_LEFT, HANDLE_BOTTOM_LEFT):
            x0 = min(x, x1 - MIN_SELECTION_SIZE)
        if self._active_handle in (HANDLE_RIGHT, HANDLE_TOP_RIGHT, HANDLE_BOTTOM_RIGHT):
            x1 = max(x, x0 + MIN_SELECTION_SIZE)
        if self._active_handle in (HANDLE_TOP, HANDLE_TOP_LEFT, HANDLE_TOP_RIGHT):
            y0 = min(y, y1 - MIN_SELECTION_SIZE)
        if self._active_handle in (HANDLE_BOTTOM, HANDLE_BOTTOM_LEFT, HANDLE_BOTTOM_RIGHT):
            y1 = max(y, y0 + MIN_SELECTION_SIZE)

        return self._rect_from_bounds(
            max(0, x0),
            max(0, y0),
            min(self.image_width(), x1),
            min(self.image_height(), y1),
        )

    def _fixed_ratio_resized_rect(self, image_pos):
        ratio = self.aspect_ratio
        x0, y0, x1, y1 = self._rect_bounds(self._drag_start_rect)
        center_x = (x0 + x1) / 2

        if self._active_handle in (HANDLE_TOP, HANDLE_TOP_LEFT, HANDLE_TOP_RIGHT):
            new_y1 = y1
            height = max(MIN_SELECTION_SIZE, new_y1 - image_pos.y())
            new_y0 = new_y1 - height
        elif self._active_handle in (
            HANDLE_BOTTOM,
            HANDLE_BOTTOM_LEFT,
            HANDLE_BOTTOM_RIGHT,
        ):
            new_y0 = y0
            height = max(MIN_SELECTION_SIZE, image_pos.y() - new_y0)
            new_y1 = new_y0 + height
        else:
            delta_y = image_pos.y() - self._drag_start.y()
            height = max(MIN_SELECTION_SIZE, self._drag_start_rect.height() + delta_y * 2)
            center_y = (y0 + y1) / 2
            new_y0 = center_y - height / 2
            new_y1 = center_y + height / 2

        width = height * ratio
        if self._active_handle in (HANDLE_LEFT, HANDLE_TOP_LEFT, HANDLE_BOTTOM_LEFT):
            new_x1 = x1
            new_x0 = new_x1 - width
        elif self._active_handle in (
            HANDLE_RIGHT,
            HANDLE_TOP_RIGHT,
            HANDLE_BOTTOM_RIGHT,
        ):
            new_x0 = x0
            new_x1 = new_x0 + width
        else:
            new_x0 = center_x - width / 2
            new_x1 = center_x + width / 2

        return self._fit_fixed_rect(new_x0, new_y0, new_x1, new_y1, ratio)

    def _fit_fixed_rect(self, x0, y0, x1, y1, ratio):
        width = x1 - x0
        height = y1 - y0
        scale = min(
            1.0,
            self.image_width() / max(1, width),
            self.image_height() / max(1, height),
        )
        width *= scale
        height = width / ratio

        if x0 < 0:
            x1 = width
            x0 = 0
        elif x1 > self.image_width():
            x1 = self.image_width()
            x0 = x1 - width
        else:
            x1 = x0 + width

        if y0 < 0:
            y1 = height
            y0 = 0
        elif y1 > self.image_height():
            y1 = self.image_height()
            y0 = y1 - height
        else:
            y1 = y0 + height
        return self._rect_from_bounds(x0, y0, x1, y1)

    def _draw_selection(self, painter, image_rect, color, label):
        if image_rect.isNull():
            return

        rect = self._image_to_widget_rect(image_rect)
        painter.setPen(QPen(color, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)

        label_y = max(14, rect.top() - 4)
        painter.drawText(rect.left(), label_y, label)

        painter.setBrush(QColor("#ffffff"))
        for handle_rect in self._handle_rects(rect).values():
            painter.drawRect(handle_rect)
        painter.setBrush(Qt.NoBrush)

    def _page1_label(self):
        return "Page" if self.selection_mode == SELECTION_SPREAD else "Page1"

    def _hit_test(self, widget_pos):
        for name, image_rect in reversed(self._selection_items()):
            if image_rect.isNull():
                continue
            widget_rect = self._image_to_widget_rect(image_rect)
            for handle, handle_rect in self._handle_rects(widget_rect).items():
                if handle_rect.contains(widget_pos):
                    return name, handle
            if widget_rect.contains(widget_pos):
                return name, None
        return None

    def _update_cursor(self, widget_pos):
        target = self._hit_test(widget_pos)
        if target is None:
            self.setCursor(QCursor(Qt.ArrowCursor))
            return

        _, handle = target
        cursors = {
            None: Qt.SizeAllCursor,
            HANDLE_LEFT: (
                Qt.SizeVerCursor if self.aspect_ratio is not None else Qt.SizeHorCursor
            ),
            HANDLE_RIGHT: (
                Qt.SizeVerCursor if self.aspect_ratio is not None else Qt.SizeHorCursor
            ),
            HANDLE_TOP: Qt.SizeVerCursor,
            HANDLE_BOTTOM: Qt.SizeVerCursor,
            HANDLE_TOP_LEFT: Qt.SizeFDiagCursor,
            HANDLE_TOP_RIGHT: Qt.SizeBDiagCursor,
            HANDLE_BOTTOM_LEFT: Qt.SizeBDiagCursor,
            HANDLE_BOTTOM_RIGHT: Qt.SizeFDiagCursor,
        }
        self.setCursor(QCursor(cursors[handle]))

    def _selection_items(self):
        items = [("rect_p1", self.rect_p1)]
        if self.selection_mode == SELECTION_TWO_PAGE:
            items.append(("rect_p2", self.rect_p2))
        return items

    def _rect_by_name(self, name):
        return getattr(self, name)

    def _set_rect_by_name(self, name, rect):
        setattr(self, name, rect)

    def _should_sync_two_page_size(self):
        return (
            self._operation == "resize"
            and self.selection_mode == SELECTION_TWO_PAGE
            and self.aspect_ratio is not None
        )

    def _sync_other_rect_size(self, source_rect):
        other_name = "rect_p2" if self._active_rect_name == "rect_p1" else "rect_p1"
        other_rect = self._rect_by_name(other_name)
        if other_rect.isNull():
            return

        center = other_rect.center()
        width = source_rect.width()
        height = source_rect.height()
        x = center.x() - width // 2
        y = center.y() - height // 2
        x = min(max(0, x), self.image_width() - width)
        y = min(max(0, y), self.image_height() - height)
        self._set_rect_by_name(other_name, QRect(x, y, width, height))

    def _reset_operation(self):
        self._operation = None
        self._active_rect_name = None
        self._active_handle = None
        self._drag_start = QPoint()
        self._drag_start_rect = QRect()

    def _reset_selection(self):
        """設定変更後の選択枠を画像中央の初期状態へ戻す。"""
        self.rect_p1 = QRect()
        self.rect_p2 = QRect()
        self._reset_operation()
        if not self._pixmap.isNull():
            self._create_initial_selection()
        self.update()

    def _display_rect(self):
        """現在の倍率でプレビュー画像を中央配置する表示矩形を返す。"""
        if self._pixmap.isNull():
            return QRect()

        scale = min(
            self.width() / max(1, self._pixmap.width()),
            self.height() / max(1, self._pixmap.height()),
        )
        scale *= self.zoom
        width = max(1, int(self._pixmap.width() * scale))
        height = max(1, int(self._pixmap.height() * scale))
        x = (self.width() - width) // 2
        y = (self.height() - height) // 2
        return QRect(x, y, width, height)

    def _widget_to_image_pos(self, pos, clamp=False):
        """ウィジェット座標をプレビュー画像の元座標へ変換する。"""
        display_rect = self._display_rect()
        if display_rect.isNull():
            return None
        if not clamp and not display_rect.contains(pos):
            return None

        x = round((pos.x() - display_rect.x()) * self._pixmap.width() / display_rect.width())
        y = round((pos.y() - display_rect.y()) * self._pixmap.height() / display_rect.height())
        x = min(max(0, x), self._pixmap.width())
        y = min(max(0, y), self._pixmap.height())
        return QPoint(x, y)

    def _image_to_widget_rect(self, rect):
        """プレビュー画像の元座標矩形をウィジェット座標へ変換する。"""
        display_rect = self._display_rect()
        x = round(display_rect.x() + rect.x() * display_rect.width() / self.image_width())
        y = round(display_rect.y() + rect.y() * display_rect.height() / self.image_height())
        width = round(rect.width() * display_rect.width() / self.image_width())
        height = round(rect.height() * display_rect.height() / self.image_height())
        return QRect(x, y, width, height)

    @staticmethod
    def _handle_rects(rect):
        half = HANDLE_SIZE // 2
        points = {
            HANDLE_LEFT: QPoint(rect.left(), rect.center().y()),
            HANDLE_RIGHT: QPoint(rect.right(), rect.center().y()),
            HANDLE_TOP: QPoint(rect.center().x(), rect.top()),
            HANDLE_BOTTOM: QPoint(rect.center().x(), rect.bottom()),
            HANDLE_TOP_LEFT: rect.topLeft(),
            HANDLE_TOP_RIGHT: rect.topRight(),
            HANDLE_BOTTOM_LEFT: rect.bottomLeft(),
            HANDLE_BOTTOM_RIGHT: rect.bottomRight(),
        }
        return {
            name: QRect(point.x() - half, point.y() - half, HANDLE_SIZE, HANDLE_SIZE)
            for name, point in points.items()
        }

    @staticmethod
    def _rect_bounds(rect):
        return rect.x(), rect.y(), rect.x() + rect.width(), rect.y() + rect.height()

    @staticmethod
    def _rect_from_bounds(x0, y0, x1, y1):
        return QRect(round(x0), round(y0), round(x1 - x0), round(y1 - y0))

    @staticmethod
    def _scaled_rect(rect, old_width, old_height, new_width, new_height):
        if rect.isNull():
            return QRect()
        return QRect(
            round(rect.x() * new_width / old_width),
            round(rect.y() * new_height / old_height),
            round(rect.width() * new_width / old_width),
            round(rect.height() * new_height / old_height),
        )
