from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel

SELECTION_SINGLE_PAGE = "single_page"
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

LEFT_HANDLES = {HANDLE_LEFT, HANDLE_TOP_LEFT, HANDLE_BOTTOM_LEFT}
RIGHT_HANDLES = {HANDLE_RIGHT, HANDLE_TOP_RIGHT, HANDLE_BOTTOM_RIGHT}
TOP_HANDLES = {HANDLE_TOP, HANDLE_TOP_LEFT, HANDLE_TOP_RIGHT}
BOTTOM_HANDLES = {HANDLE_BOTTOM, HANDLE_BOTTOM_LEFT, HANDLE_BOTTOM_RIGHT}

RESIZE_FREE = "free"
RESIZE_FREE_SYNC = "free_sync"
RESIZE_FIXED = "fixed"
RESIZE_FIXED_SYNC = "fixed_sync"


class SelectionLabel(QLabel):
    """画像上で移動・リサイズ可能な切り抜き矩形を管理する。"""

    def __init__(self):
        super().__init__()
        self._pixmap = QPixmap()
        self.zoom = 1.0
        self.rect_p1 = QRect()
        self.rect_p2 = QRect()
        self.selection_mode = SELECTION_SINGLE_PAGE
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
        """シングルページまたは2ページへ切り替え、既存の選択枠を破棄する。"""
        if mode not in (SELECTION_SINGLE_PAGE, SELECTION_TWO_PAGE):
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

        image_pos = self._widget_to_image_pos(event.pos(), allow_outside=True)
        if image_pos is None:
            return

        if self._operation == "move":
            rect = self._moved_rect(image_pos)
            self._set_rect_by_name(self._active_rect_name, rect)
        else:
            self._apply_resize_drag(image_pos, event.modifiers())
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
        if self.selection_mode == SELECTION_SINGLE_PAGE:
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
        self._draw_selection(
            painter, self.rect_p1, QColor("#e00000"), self._page1_label()
        )
        if self.selection_mode == SELECTION_TWO_PAGE:
            self._draw_selection(painter, self.rect_p2, QColor("#0057d9"), "Page 2")

    def _create_initial_selection(self):
        """現在の設定に従う選択枠を画像中央へ生成する。"""
        image_width = self.image_width()
        image_height = self.image_height()
        gap = max(8, round(image_width * 0.02))

        if self.selection_mode == SELECTION_SINGLE_PAGE:
            width, height = self._initial_size(image_width, image_height, image_width)
            self.rect_p1 = self._centered_rect(width, height, image_width / 2)
            self.rect_p2 = QRect()
            return

        available_width = max(MIN_SELECTION_SIZE, (image_width - gap) / 2)
        width, height = self._initial_size(image_width, image_height, available_width)
        total_width = width * 2 + gap
        left = (image_width - total_width) / 2
        top = (image_height - height) / 2
        self.rect_p2 = QRect(round(left), round(top), round(width), round(height))
        self.rect_p1 = QRect(
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
        if self._active_handle in (
            HANDLE_BOTTOM,
            HANDLE_BOTTOM_LEFT,
            HANDLE_BOTTOM_RIGHT,
        ):
            y1 = max(y, y0 + MIN_SELECTION_SIZE)

        return self._rect_from_bounds(
            max(0, x0),
            max(0, y0),
            min(self.image_width(), x1),
            min(self.image_height(), y1),
        )

    def _fixed_ratio_size_from_drag(self, image_pos):
        ratio = self.aspect_ratio
        x0, y0, x1, y1 = self._rect_bounds(self._drag_start_rect)

        if self._active_handle in (HANDLE_LEFT, HANDLE_RIGHT):
            fixed_x = x1 if self._active_handle == HANDLE_LEFT else x0
            width = max(MIN_SELECTION_SIZE, abs(fixed_x - image_pos.x()))
            return width, width / ratio

        if self._active_handle in TOP_HANDLES:
            height = max(MIN_SELECTION_SIZE, y1 - image_pos.y())
        elif self._active_handle in BOTTOM_HANDLES:
            height = max(MIN_SELECTION_SIZE, image_pos.y() - y0)
        else:
            delta_y = image_pos.y() - self._drag_start.y()
            height = max(
                MIN_SELECTION_SIZE, self._drag_start_rect.height() + delta_y * 2
            )
        return height * ratio, height

    def _apply_resize_drag(self, image_pos, modifiers):
        """リサイズ経路の入口。モード判定、サイズ算出、反映をここで束ねる。"""
        mode = self._resize_mode(modifiers)
        if mode == RESIZE_FREE:
            rect = self._freely_resized_rect(image_pos)
            self._set_rect_by_name(self._active_rect_name, rect)
            return

        width, height = self._resize_size_from_drag(image_pos, mode)
        width, height = self._bounded_resize_size(
            width,
            height,
            preserve_ratio=mode in (RESIZE_FIXED, RESIZE_FIXED_SYNC),
            synchronize=mode in (RESIZE_FREE_SYNC, RESIZE_FIXED_SYNC),
        )
        self._apply_resized_size(
            width,
            height,
            synchronize=mode in (RESIZE_FREE_SYNC, RESIZE_FIXED_SYNC),
        )

    def _resize_mode(self, modifiers):
        """現在の設定と修飾キーから、どのリサイズ経路を通すかを決める。"""
        if self.aspect_ratio is None:
            if self._should_sync_free_resize(modifiers):
                return RESIZE_FREE_SYNC
            return RESIZE_FREE
        if self._should_sync_two_page_size():
            return RESIZE_FIXED_SYNC
        return RESIZE_FIXED

    def _resize_size_from_drag(self, image_pos, mode):
        """各モード固有の方法で、最終適用前の width/height を求める。"""
        if mode in (RESIZE_FIXED, RESIZE_FIXED_SYNC):
            return self._fixed_ratio_size_from_drag(image_pos)

        rect = self._freely_resized_rect(image_pos)
        return rect.width(), rect.height()

    def _apply_resized_size(self, width, height, synchronize=False):
        """算出済みサイズをアクティブ枠へ反映し、必要なら相手枠にも同期する。"""
        self._set_rect_by_name(
            self._active_rect_name,
            self._anchored_rect_from_reference(
                self._drag_start_rect,
                width,
                height,
                self._active_handle,
            ),
        )
        if synchronize:
            self._sync_other_rect_size(width, height)

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
        return "Page" if self.selection_mode == SELECTION_SINGLE_PAGE else "Page 1"

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
            HANDLE_LEFT: Qt.SizeHorCursor,
            HANDLE_RIGHT: Qt.SizeHorCursor,
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

    def _should_sync_free_resize(self, modifiers):
        return (
            self._operation == "resize"
            and self.selection_mode == SELECTION_TWO_PAGE
            and self.aspect_ratio is None
            and bool(modifiers & Qt.ShiftModifier)
        )

    def _sync_other_rect_size(self, width, height):
        other_name = "rect_p2" if self._active_rect_name == "rect_p1" else "rect_p1"
        other_rect = self._rect_by_name(other_name)
        if other_rect.isNull():
            return

        self._set_rect_by_name(
            other_name,
            self._anchored_rect_from_reference(
                other_rect,
                width,
                height,
                self._active_handle,
            ),
        )

    def _other_active_rect(self):
        other_name = "rect_p2" if self._active_rect_name == "rect_p1" else "rect_p1"
        return self._rect_by_name(other_name)

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

    def _widget_to_image_pos(self, pos, allow_outside=False):
        """ウィジェット座標をプレビュー画像の元座標へ変換する。"""
        display_rect = self._display_rect()
        if display_rect.isNull():
            return None
        if not allow_outside and not display_rect.contains(pos):
            return None

        x = round(
            (pos.x() - display_rect.x()) * self._pixmap.width() / display_rect.width()
        )
        y = round(
            (pos.y() - display_rect.y()) * self._pixmap.height() / display_rect.height()
        )
        return QPoint(x, y)

    def _image_to_widget_rect(self, rect):
        """プレビュー画像の元座標矩形をウィジェット座標へ変換する。"""
        display_rect = self._display_rect()
        x = round(
            display_rect.x() + rect.x() * display_rect.width() / self.image_width()
        )
        y = round(
            display_rect.y() + rect.y() * display_rect.height() / self.image_height()
        )
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
    def _horizontal_anchor_mode(handle):
        if handle in LEFT_HANDLES:
            return "max"
        if handle in RIGHT_HANDLES:
            return "min"
        return "center"

    @staticmethod
    def _vertical_anchor_mode(handle):
        if handle in TOP_HANDLES:
            return "max"
        if handle in BOTTOM_HANDLES:
            return "min"
        return "center"

    @staticmethod
    def _anchored_coordinate(minimum, maximum, mode):
        if mode == "min":
            return minimum
        if mode == "max":
            return maximum
        return (minimum + maximum) / 2

    @staticmethod
    def _anchored_origin(anchor, size, mode, inclusive=False):
        if mode == "min":
            return round(anchor)
        if mode == "max":
            offset = size - 1 if inclusive else size
            return round(anchor - offset)
        return round(anchor - size / 2)

    @classmethod
    def _anchored_bounds(cls, anchor, size, mode):
        start = cls._anchored_origin(anchor, size, mode)
        return start, start + size

    @classmethod
    def _anchored_rect_from_reference(cls, rect, width, height, handle):
        x0, y0, x1, y1 = cls._rect_bounds(rect)
        x_mode = cls._horizontal_anchor_mode(handle)
        y_mode = cls._vertical_anchor_mode(handle)
        anchor_x = cls._anchored_coordinate(x0, x1, x_mode)
        anchor_y = cls._anchored_coordinate(y0, y1, y_mode)
        new_x0, new_x1 = cls._anchored_bounds(anchor_x, width, x_mode)
        new_y0, new_y1 = cls._anchored_bounds(anchor_y, height, y_mode)
        return cls._rect_from_bounds(new_x0, new_y0, new_x1, new_y1)

    def _bounded_resize_size(
        self,
        width,
        height,
        preserve_ratio,
        synchronize,
    ):
        """画像外にはみ出さないサイズへ補正する。同期時は相手枠の制約も見る。"""
        rects = [self._drag_start_rect]
        if synchronize:
            rects.append(self._other_active_rect())

        if preserve_ratio:
            return self._bounded_fixed_ratio_size(width, height, *rects)
        return self._bounded_size(width, height, *rects)

    def _bounded_fixed_ratio_size(self, width, height, *rects):
        max_scale = 1.0
        for rect in rects:
            if rect.isNull():
                continue
            max_width, max_height = self._max_fixed_ratio_size_for_rect(
                rect,
                self._active_handle,
            )
            max_scale = min(
                max_scale,
                max_width / max(width, 1),
                max_height / max(height, 1),
            )

        if max_scale >= 1.0:
            return width, height
        return max(MIN_SELECTION_SIZE, width * max_scale), max(
            MIN_SELECTION_SIZE, height * max_scale
        )

    def _bounded_size(self, width, height, *rects):
        max_width = width
        max_height = height
        for rect in rects:
            if rect.isNull():
                continue
            rect_max_width, rect_max_height = self._max_fixed_ratio_size_for_rect(
                rect,
                self._active_handle,
            )
            max_width = min(max_width, rect_max_width)
            max_height = min(max_height, rect_max_height)
        return max(MIN_SELECTION_SIZE, max_width), max(MIN_SELECTION_SIZE, max_height)

    def _max_fixed_ratio_size_for_rect(self, rect, handle):
        x0, y0, x1, y1 = self._rect_bounds(rect)
        x_mode = self._horizontal_anchor_mode(handle)
        y_mode = self._vertical_anchor_mode(handle)
        anchor_x = self._anchored_coordinate(x0, x1, x_mode)
        anchor_y = self._anchored_coordinate(y0, y1, y_mode)
        return (
            self._max_size_for_axis(anchor_x, self.image_width(), x_mode),
            self._max_size_for_axis(anchor_y, self.image_height(), y_mode),
        )

    @staticmethod
    def _max_size_for_axis(anchor, limit, mode):
        if mode == "min":
            return max(MIN_SELECTION_SIZE, limit - anchor)
        if mode == "max":
            return max(MIN_SELECTION_SIZE, anchor)
        return max(MIN_SELECTION_SIZE, min(anchor, limit - anchor) * 2)

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
