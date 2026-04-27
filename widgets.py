from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel


class SelectionLabel(QLabel):
    """画像上でマウスドラッグして矩形を選択するクラス"""

    def __init__(self):
        """切り抜き矩形の状態を初期化する。"""
        super().__init__()
        self.setScaledContents(True)
        self.rect_p1 = QRect()
        self.rect_p2 = QRect()
        self.mode = 1  # 1: 1ページ目, 2: 2ページ目
        self.spread_mode = True
        self.start_pos = QPoint()

    def mousePressEvent(self, event):
        """ドラッグ開始位置を記録する。"""
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()

    def mouseMoveEvent(self, event):
        """ドラッグ中の位置から現在モードの選択矩形を更新する。"""
        if event.buttons() & Qt.LeftButton:
            rect = QRect(self.start_pos, event.pos()).normalized()
            if self.mode == 1:
                self.rect_p1 = rect
            else:
                self.rect_p2 = rect
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
        super().paintEvent(event)
        painter = QPainter(self)
        if not self.rect_p1.isNull():
            painter.setPen(QPen(QColor(255, 0, 0), 2))
            painter.drawRect(self.rect_p1)
            painter.drawText(self.rect_p1.topLeft(), "Page 1" if self.spread_mode else "Page")
        if self.spread_mode and not self.rect_p2.isNull():
            painter.setPen(QPen(QColor(0, 0, 255), 2))
            painter.drawRect(self.rect_p2)
            painter.drawText(self.rect_p2.topLeft(), "Page 2")
