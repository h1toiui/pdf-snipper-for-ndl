from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel


class SelectionLabel(QLabel):
    """画像上でマウスドラッグして矩形を選択するクラス"""

    def __init__(self):
        """切り抜き矩形の状態を初期化する。"""
        super().__init__()
        self._pixmap = QPixmap()
        self.zoom = 1.0
        self.rect_p1 = QRect()
        self.rect_p2 = QRect()
        self.mode = 1  # 1: 1ページ目, 2: 2ページ目
        self.spread_mode = True
        self.start_pos = QPoint()
        self.dragging = False
        self.setMouseTracking(True)

    def setPixmap(self, pixmap):
        """プレビュー画像を設定し、表示倍率を等倍へ戻す。"""
        self._pixmap = QPixmap(pixmap)
        self.zoom = 1.0
        self.update()

    def pixmap(self):
        """現在のプレビュー画像を返す。"""
        return self._pixmap

    def clear(self):
        """プレビュー画像を消す。"""
        self._pixmap = QPixmap()
        self.update()

    def image_width(self):
        """プレビュー画像の元幅を返す。"""
        return max(1, self._pixmap.width())

    def image_height(self):
        """プレビュー画像の元高さを返す。"""
        return max(1, self._pixmap.height())

    def mousePressEvent(self, event):
        """ドラッグ開始位置を記録する。"""
        if event.button() == Qt.LeftButton:
            image_pos = self._widget_to_image_pos(event.pos())
            if image_pos is not None:
                self.start_pos = image_pos
                self.dragging = True

    def mouseMoveEvent(self, event):
        """ドラッグ中の位置から現在モードの選択矩形を更新する。"""
        if event.buttons() & Qt.LeftButton and self.dragging:
            image_pos = self._widget_to_image_pos(event.pos(), clamp=True)
            if image_pos is None:
                return
            rect = QRect(self.start_pos, image_pos).normalized()
            if self.mode == 1:
                self.rect_p1 = rect
            else:
                self.rect_p2 = rect
            self.update()

    def mouseReleaseEvent(self, event):
        """ドラッグ終了後に開始位置をリセットする。"""
        if event.button() == Qt.LeftButton:
            self.start_pos = QPoint()
            self.dragging = False

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
        self.update()

    def selected_rects(self):
        """現在のスキャンモードで有効な切り抜き矩形を返す。"""
        if not self.spread_mode:
            return [self.rect_p1] if not self.rect_p1.isNull() else []
        return [rect for rect in (self.rect_p1, self.rect_p2) if not rect.isNull()]

    def set_spread_mode(self, enabled):
        """見開きモードの有効/無効を切り替える。"""
        self.spread_mode = enabled
        self.mode = 1
        if not enabled:
            self.rect_p2 = QRect()
        self.update()

    def toggle_mode(self):
        """見開き時に1ページ目と2ページ目の編集対象を切り替える。"""
        if not self.spread_mode:
            self.mode = 1
            return self.mode
        self.mode = 2 if self.mode == 1 else 1
        return self.mode

    def paintEvent(self, event):
        """プレビュー画像上に選択済みの切り抜き矩形を描画する。"""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#eeeeee"))
        painter.setPen(QPen(QColor("#cccccc"), 2))
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))

        if self._pixmap.isNull():
            return

        display_rect = self._display_rect()
        painter.drawPixmap(display_rect, self._pixmap)

        if not self.rect_p1.isNull():
            painter.setPen(QPen(QColor(255, 0, 0), 2))
            rect = self._image_to_widget_rect(self.rect_p1)
            painter.drawRect(rect)
            painter.drawText(rect.topLeft(), "Page 1" if self.spread_mode else "Page")
        if self.spread_mode and not self.rect_p2.isNull():
            painter.setPen(QPen(QColor(0, 0, 255), 2))
            rect = self._image_to_widget_rect(self.rect_p2)
            painter.drawRect(rect)
            painter.drawText(rect.topLeft(), "Page 2")

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
